import asyncio
import argparse
import io
import json
import os
import queue
import sys
import threading

import numpy as np
import psutil
import soundcard as sc
import soundfile as sf
import websockets


WS_URL = "ws://127.0.0.1:8000/ws/transcribe"
SAMPLE_RATE = 48000
CHANNELS = 2
CHUNK_SECONDS = 3.0
# 低於此音量視為靜音;單一程式的音量比整個系統混音小,門檻要更低
SILENCE_RMS_SYSTEM = 0.02
SILENCE_RMS_PROCESS = 0.002

audio_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=10)


def capture_system_audio():
    speaker = sc.default_speaker()
    print(f"Using speaker: {speaker.name}")

    mic = sc.get_microphone(id=str(speaker.name), include_loopback=True)

    with mic.recorder(samplerate=SAMPLE_RATE, channels=CHANNELS) as recorder:
        while True:
            yield recorder.record(numframes=SAMPLE_RATE * CHUNK_SECONDS)


def capture_process_audio(pid: int):
    # 延遲 import:只錄系統音訊時不需要 proc-tap
    from proctap import ProcessAudioCapture

    print(f"Capturing audio from PID {pid}")

    pcm_queue: queue.Queue[bytes] = queue.Queue()
    capture = ProcessAudioCapture(pid, on_data=lambda pcm, _frames: pcm_queue.put(pcm))

    # 原生模組在系統不支援時會悄悄退回整個系統擷取,那會讓「只錄這個程式」失效
    if not capture._backend._native.is_process_specific():
        capture.close()
        raise RuntimeError("此系統無法使用程序專屬擷取(需要 Windows 10 2004 以上)")

    capture.start()

    chunk_frames = int(SAMPLE_RATE * CHUNK_SECONDS)
    pending: list[np.ndarray] = []
    pending_frames = 0

    try:
        while True:
            try:
                pcm = pcm_queue.get(timeout=5)
            except queue.Empty:
                # 程式沒在發聲時可能不會有資料,只有程式結束才需要離開
                if not psutil.pid_exists(pid):
                    print(f"Process {pid} exited.")
                    return
                continue

            # proc-tap 固定輸出 48kHz / 2ch / float32
            frames = np.frombuffer(pcm, dtype=np.float32).reshape(-1, CHANNELS)
            pending.append(frames)
            pending_frames += len(frames)

            if pending_frames >= chunk_frames:
                yield np.concatenate(pending)
                pending = []
                pending_frames = 0
    finally:
        capture.close()


def recording_worker(loop: asyncio.AbstractEventLoop, pid: int | None):
    try:
        source = capture_process_audio(pid) if pid else capture_system_audio()
        silence_rms = SILENCE_RMS_PROCESS if pid else SILENCE_RMS_SYSTEM

        for frames in source:
            if frames is None or len(frames) == 0:
                print("No audio captured.")
                continue

            rms = np.sqrt(np.mean(np.square(frames)))

            if rms < silence_rms:
                continue

            buffer = io.BytesIO()
            sf.write(buffer, frames, SAMPLE_RATE, format="WAV")
            audio_bytes = buffer.getvalue()

            def push_chunk(audio_bytes=audio_bytes):
                if audio_queue.full():
                    try:
                        dropped = audio_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass

                audio_queue.put_nowait(audio_bytes)

            loop.call_soon_threadsafe(push_chunk)
    except Exception as e:
        print(f"Capture error: {e}")

    # 擷取結束(程式關閉或失敗)就整個結束,讓 Electron 知道
    print("Capture stopped.")
    sys.stdout.flush()
    os._exit(1)


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


async def main(pid: int | None):
    loop = asyncio.get_running_loop()

    thread = threading.Thread(
        target=recording_worker,
        args=(loop, pid),
        daemon=True
    )
    thread.start()

    await send_audio()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, default=None, help="只擷取此行程(含子行程)的音訊;省略則擷取整個系統")
    args = parser.parse_args()

    asyncio.run(main(args.pid))