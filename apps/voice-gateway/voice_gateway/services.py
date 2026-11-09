"""Real STT, Hermes and TTS. Heavy imports stay inside so tests run without them."""
import asyncio
import json
import os

import httpx


class ParakeetStt:
    """NVIDIA Parakeet TDT v3 (multilingual, int8 ONNX on CPU). Measured on the server with the user's
    own voice notes: Whisper large-v3-turbo quality at ~0.4-0.6 s per phrase (Whisper base: ~0.85 s,
    with errors)."""

    def __init__(self):
        self.model = None

    def load(self):
        if self.model is None:
            import onnx_asr
            self.model = onnx_asr.load_model(os.environ.get("STT_MODEL", "nemo-parakeet-tdt-0.6b-v3"),
                                             quantization="int8")

    def _transcribe(self, pcm16):
        import numpy as np
        self.load()
        audio = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768
        if len(audio) < 1600:  # under 0.1 s: nothing to say
            return ""
        return self.model.recognize(audio, sample_rate=16000).strip()

    async def transcribe(self, pcm16):
        return await asyncio.to_thread(self._transcribe, pcm16)


class HermesClient:
    """Streams /v1/responses text deltas; cancelling the consumer closes the SSE, which interrupts Hermes."""

    def __init__(self):
        self.url = os.environ.get("HERMES_URL", "http://hermes:8642").rstrip("/") + "/v1/responses"
        self.key = os.environ["API_SERVER_KEY"]
        self.conversation = os.environ.get("HERMES_CONVERSATION", "finnip-voice")
        self.model = os.environ.get("VOICE_MODEL") or None
        self.http = httpx.AsyncClient(timeout=httpx.Timeout(10, read=120))

    async def stream(self, text):
        body = {"model": self.model or "hermes", "input": text, "stream": True, "store": True,
                "conversation": self.conversation, "model_options": {"reasoning": {"enabled": False}}}
        if self.model:
            body["provider"] = os.environ.get("VOICE_PROVIDER", "anthropic")
        headers = {"Authorization": f"Bearer {self.key}"}
        async with self.http.stream("POST", self.url, json=body, headers=headers) as resp:
            if resp.status_code != 200:
                raise RuntimeError(f"Hermes respondió HTTP {resp.status_code}")
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                event = json.loads(line[5:])
                if event.get("type") == "response.output_text.delta":
                    yield event.get("delta", "")
                elif event.get("type") == "response.failed":
                    raise RuntimeError("Hermes no pudo completar la respuesta")


class EdgeTts:
    def __init__(self):
        self.voice = os.environ.get("TTS_VOICE", "es-MX-JorgeNeural")

    async def synthesize(self, text):
        import edge_tts
        audio = bytearray()
        async for chunk in edge_tts.Communicate(text, self.voice).stream():
            if chunk["type"] == "audio":
                audio += chunk["data"]
        return bytes(audio)
