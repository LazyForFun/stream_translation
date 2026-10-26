import json
import os
import uuid
import asyncio
import re
import time
import uvicorn

from pathlib import Path
from collections import Counter, deque

from fastapi import FastAPI, UploadFile, File, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from services.translator import Translator
from services.segmenter import SentenceSegmenter
from pydantic import BaseModel

from dotenv import load_dotenv
load_dotenv()

from services.secure_storage import (
    save_api_key_encrypted,
    load_api_key_encrypted,
    clear_saved_api_key,
)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ApiKeyPayload(BaseModel):
    api_key: str

# transcriber = Transcriber(model_name="medium")

transcriber = None

def get_transcriber():
    global transcriber
    if transcriber is None:
        from services.transcriber import Transcriber
        transcriber = Transcriber()
    return transcriber

translator = Translator()

saved_api_key = load_api_key_encrypted()
if saved_api_key:
    translator.set_api_key(saved_api_key)

translation_context_history = deque(maxlen=2)

TEMP_DIR = Path("temp")
TEMP_DIR.mkdir(exist_ok=True)

language_history = deque(maxlen=10)

ALLOWED_LANGUAGES = {"ko", "ja", "en", "zh"}

subtitle_clients = set()

async def broadcast_subtitle(payload: dict):

    dead_clients = []
    for client in subtitle_clients:
        try:
            await client.send_text(json.dumps(payload, ensure_ascii=False))
        except Exception:
            dead_clients.append(client)

    for client in dead_clients:
        subtitle_clients.discard(client)

def get_stable_language(current_language: str, prob: float) -> str:
    # 只接受你真的可能遇到的語言
    allowed_languages = {"ko", "en", "ja"}

    if current_language not in allowed_languages:
        return "ko"

    # 高信心才記錄
    if prob >= 0.5:
        language_history.append(current_language)

    if not language_history:
        return "ko"

    counter = Counter(language_history)
    most_common_lang, count = counter.most_common(1)[0]

    # 如果韓文有出現，優先偏向韓文
    if "ko" in counter and counter["ko"] >= max(2, count):
        return "ko"

    # 如果某個語言真的連續出現很多次，才切過去
    if count >= 3:
        return most_common_lang

    # 預設仍偏韓文
    return "ko"


def should_skip_text(text: str) -> bool:
    cleaned = text.strip().lower()

    if not cleaned:
        return True

    if len(cleaned) <= 1:
        return True

    noise_patterns = [
        r"^(ha)+$",
        r"^(he)+$",
        r"^(ja)+$",
        r"^(kk)+$",
        r"^(uh)+$",
        r"^(um)+$",
        r"^(ah)+$",
        r"^(oh)+$",
        r"^(wow)+$",
        r"^(lol)+$",
        r"^(lmao)+$",
        r"^(haha)+$",
        r"^(hahaha)+$",
        r"^(ㅋㅋ)+$",
        r"^(ㅎㅎ)+$",
        r"^(哈)+$",
        r"^(哈哈)+$",
        r"^(呵)+$",
        r"^(呵呵)+$",
        r"^(啊)+$",
        r"^(哇)+$",
        r"^(www)+$",
    ]

    for pattern in noise_patterns:
        if re.fullmatch(pattern, cleaned):
            return True

    if re.fullmatch(r"(.)\1{2,}", cleaned):
        return True

    return False


@app.get("/")
def root():
    return {"ok": True}

@app.post("/set-api-key")
async def set_api_key(payload: ApiKeyPayload):
    api_key = payload.api_key.strip()

    if not api_key:
        raise HTTPException(status_code=400, detail="API key is empty")

    translator.set_api_key(api_key)
    save_api_key_encrypted(api_key)

    return {"ok": True}

@app.post("/clear-api-key")
async def clear_api_key():
    translator.clear_api_key()
    clear_saved_api_key()
    return {"ok": True}

@app.get("/api-key-status")
async def api_key_status():
    return {"has_api_key": translator.has_api_key()}


@app.post("/transcribe")
async def transcribe_file(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")

    suffix = Path(file.filename).suffix or ".tmp"
    temp_path = TEMP_DIR / f"{uuid.uuid4()}{suffix}"

    try:
        content = await file.read()
        temp_path.write_bytes(content)

        result = get_transcriber().transcribe(str(temp_path))
        return {
            "text": result["text"],
            "language": result["language"],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if temp_path.exists():
            temp_path.unlink()

@app.websocket("/ws/subtitles")
async def websocket_subtitles(ws: WebSocket):
    await ws.accept()
    print("[ws/subtitles] connected")
    subtitle_clients.add(ws)

    try:
        while True:
            await asyncio.sleep(30)
    except WebSocketDisconnect:
        print("[ws/subtitles] disconnected")
        subtitle_clients.discard(ws)
    except Exception as e:
        print("[ws/subtitles] error:", e)
        subtitle_clients.discard(ws)



async def emit_sentences(
    ws: WebSocket,
    sentences: list[str],
    chunk_index: int,
    detected_language: str,
    language_probability: float,
    language: str,
):
    for sentence in sentences:
        context_lines = list(translation_context_history)

        translated_text = await asyncio.to_thread(
            translator.translate_to_zh_tw,
            sentence,
            language,
            context_lines
        )

        translation_context_history.append(sentence)

        subtitle_payload = {
            "type": "subtitle",
            "chunk_index": chunk_index,
            "original_text": sentence,
            "translated_text": translated_text,
            "language": language,
            "raw_language": detected_language,
            "language_probability": language_probability,
            "is_final": True
        }

        await ws.send_text(json.dumps(subtitle_payload, ensure_ascii=False))
        await broadcast_subtitle(subtitle_payload)


@app.websocket("/ws/transcribe")
async def websocket_transcribe(ws: WebSocket):
    await ws.accept()
    print("[ws/transcribe] connected")
    chunk_index = 0

    segmenter = SentenceSegmenter()
    lock = asyncio.Lock()
    stable_language = "ko"

    # 靜音 chunk 不會送上來，所以要靠計時器在停頓後把 buffer 吐出
    async def pause_flusher():
        while True:
            await asyncio.sleep(0.3)
            async with lock:
                sentences = segmenter.poll()
                if sentences:
                    await emit_sentences(
                        ws, sentences, chunk_index, "", 0.0, stable_language
                    )

    flusher_task = asyncio.create_task(pause_flusher())

    try:
        while True:
            message = await ws.receive()

            if message.get("type") == "websocket.disconnect":
                break

            if "bytes" not in message or message["bytes"] is None:
                await ws.send_text(json.dumps({
                    "type": "info",
                    "message": "No audio bytes received"
                }, ensure_ascii=False))
                continue

            audio_bytes = message["bytes"]
            chunk_index += 1
            temp_path = TEMP_DIR / f"{uuid.uuid4()}.wav"

            try:
                async with lock:
                    temp_path.write_bytes(audio_bytes)

                    result = await asyncio.to_thread(
                        get_transcriber().transcribe,
                        str(temp_path)
                    )

                    original_text = result.get("text", "").strip()
                    detected_language = result.get("language", "")
                    language_probability = result.get("language_probability", 0.0)

                    # 笑聲 / 擬聲 / 雜訊不進 buffer，由停頓計時器處理收尾
                    sentences = (
                        [] if should_skip_text(original_text)
                        else segmenter.feed(original_text)
                    )

                    if sentences:
                        await emit_sentences(
                            ws,
                            sentences,
                            chunk_index,
                            detected_language,
                            language_probability,
                            stable_language,
                        )
                    else:
                        await ws.send_text(json.dumps({
                            "type": "buffering",
                            "chunk_index": chunk_index,
                            "original_text": original_text,
                            "translated_text": "",
                            "language": stable_language,
                            "raw_language": detected_language,
                            "language_probability": language_probability,
                            "is_final": False
                        }, ensure_ascii=False))

            except Exception as e:
                print(f"Chunk {chunk_index} processing error: {e}")

                await ws.send_text(json.dumps({
                    "type": "error",
                    "chunk_index": chunk_index,
                    "message": str(e)
                }, ensure_ascii=False))

            finally:
                if temp_path.exists():
                    temp_path.unlink()

    except WebSocketDisconnect:
        print("WebSocket client disconnected")
    except Exception as e:
        print("WebSocket fatal error:", e)
    finally:
        flusher_task.cancel()

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")