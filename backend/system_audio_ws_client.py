import asyncio
import io
import json
import threading

import numpy as np
import soundcard as sc
import soundfile as sf
import websockets


WS_URL = "ws://127.0.0.1:8000/ws/transcribe"
SAMPLE_RATE = 48000
CHANNELS = 2
CHUNK_SECONDS = 3.0

audio_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=10)


def recording_worker(loop: asyncio.AbstractEventLoop):
    speaker = sc.default_speaker()
    print(f"Using speaker: {speaker.name}")

    mic = sc.get_microphone(id=str(speaker.name), include_loopback=True)

    with mic.recorder(samplerate=SAMPLE_RATE, channels=CHANNELS) as recorder:
        chunk_index = 0

        while True:
            chunk_index += 1

            frames = recorder.record(numframes=SAMPLE_RATE * CHUNK_SECONDS)

            if frames is None or len(frames) == 0:
                print("No audio captured.")
                continue

            rms = np.sqrt(np.mean(np.square(frames)))

            if rms < 0.02:
                continue

            buffer = io.BytesIO()
            sf.write(buffer, frames, SAMPLE_RATE, format="WAV")
            audio_bytes = buffer.getvalue()

            def push_chunk():
                if audio_queue.full():
                    try:
                        dropped = audio_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass

                audio_queue.put_nowait(audio_bytes)

            loop.call_soon_threadsafe(push_chunk)


async def receive_responses(ws):
    async for raw_response in ws:
        data = json.loads(raw_response)

        if data.get("type") == "error":
            print(f"Server error on chunk {data.get('chunk_index')}: {data.get('message')}")
            continue

        if data.get("type") == "buffering":
            continue

        original_text = data.get("original_text", "")
        translated_text = data.get("translated_text", "")

        if original_text.strip():
            print(f"[{data.get('chunk_index')}] {translated_text or original_text}")


async def send_audio():
    while True:
        try:
            async with websockets.connect(
                WS_URL,
                max_size=10_000_000,
                ping_interval=20,
                ping_timeout=60,
                close_timeout=10,
            ) as ws:
                print("WebSocket connected.")

                # 伺服器可能在停頓後主動推字幕，所以收發分開
                receiver = asyncio.create_task(receive_responses(ws))
                try:
                    while True:
                        audio_bytes = await audio_queue.get()
                        await ws.send(audio_bytes)
                finally:
                    receiver.cancel()

        except websockets.ConnectionClosed as e:
            print(f"WebSocket disconnected: {e}. Reconnecting in 3 seconds...")
            await asyncio.sleep(3)
        except Exception as e:
            print(f"Sender error: {e}")
            print("Reconnect in 3 seconds...")
            await asyncio.sleep(3)


async def main():
    loop = asyncio.get_running_loop()

    thread = threading.Thread(
        target=recording_worker,
        args=(loop,),
        daemon=True
    )
    thread.start()

    await send_audio()


if __name__ == "__main__":
    asyncio.run(main())