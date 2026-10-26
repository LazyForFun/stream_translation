import asyncio
import json
from pathlib import Path
import websockets

AUDIO_FILES = [
    "c1.mp3",
    "c2.mp3",
    "c3.mp3",
]

async def main():
    uri = "ws://127.0.0.1:8000/ws/transcribe"

    async with websockets.connect(uri, max_size=10_000_000) as ws:
        for audio_file in AUDIO_FILES:
            print(f"Sending: {audio_file}")
            audio_bytes = Path(audio_file).read_bytes()
            await ws.send(audio_bytes)

            raw_response = await ws.recv()
            data = json.loads(raw_response)

            print(f"type: {data.get('type')}")
            print(f"chunk_index: {data.get('chunk_index')}")
            print(f"original_text: {data.get('original_text')}")
            print(f"translated_text: {data.get('translated_text')}")
            print(f"language: {data.get('language')}")
            print(f"is_final: {data.get('is_final')}")
            print("-" * 50)

            await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())