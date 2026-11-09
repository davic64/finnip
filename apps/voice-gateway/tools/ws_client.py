"""Reference client for /ws (also the ESP32's model): sends a WAV and reports latency.

Usage: python tools/ws_client.py frase.wav [ws://127.0.0.1:8765/ws] [usuario@tailnet]
The WAV must be PCM16 mono 16 kHz (ffmpeg -i in.ogg -ac 1 -ar 16000 -sample_fmt s16 frase.wav).
"""
import asyncio
import json
import sys
import time
import wave

import websockets

CHUNK = 16000 * 2 // 10  # 100 ms frames, like a live mic


async def main(path, url, user):
    with wave.open(path) as w:
        assert (w.getnchannels(), w.getframerate(), w.getsampwidth()) == (1, 16000, 2), "WAV PCM16 mono 16 kHz"
        pcm = w.readframes(w.getnframes())
    async with websockets.connect(url, additional_headers={"Tailscale-User-Login": user}) as ws:
        await ws.send(json.dumps({"type": "hello", "client": "ws_client", "version": 1}))
        print(await ws.recv())
        for i in range(0, len(pcm), CHUNK):
            await ws.send(pcm[i:i + CHUNK])
        await ws.send(json.dumps({"type": "utterance_end"}))
        t0, first_audio, total = time.time(), None, 0
        async for msg in ws:
            if isinstance(msg, bytes):
                first_audio = first_audio or time.time() - t0
                total += len(msg)
                continue
            event = json.loads(msg)
            print(f"{time.time() - t0:6.2f}s {event}")
            if event["type"] == "done":
                break
    print(f"primer audio: {first_audio:.2f}s, audio total: {total} bytes" if first_audio else "sin audio")


if __name__ == "__main__":
    args = sys.argv[1:] + [None, None]
    asyncio.run(main(args[0], args[1] or "ws://127.0.0.1:8765/ws", args[2] or "david@example.com"))
