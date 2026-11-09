"""Real STT, Hermes and TTS. Heavy imports stay inside so tests run without them."""
import asyncio
import json
import os
import re

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


class ICloudCalendar:
    """Agenda panel: loads the finnip-calendar Hermes plugin (mounted read only) and uses its CalDAV
    reader, so iCloud is spoken to by one piece of code. Credentials come from the environment."""
    def __init__(self, path):
        import importlib.util
        spec = importlib.util.spec_from_file_location("finnip_calendar", path)
        self.plugin = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.plugin)
    async def events(self, start, end, limit=100):
        return await asyncio.to_thread(self.plugin.list_events, start, end, limit)
class EdgeTts:
    def __init__(self):
        self.voice = os.environ.get("TTS_VOICE", "es-MX-JorgeNeural")

    async def synthesize(self, text):
        import edge_tts
        text = re.sub(r"\bfinnip\b", "Fínnip", text, flags=re.IGNORECASE)  # stress on the first i
        audio = bytearray()
        async for chunk in edge_tts.Communicate(text, self.voice).stream():
            if chunk["type"] == "audio":
                audio += chunk["data"]
        return bytes(audio)


def host_stats(disk_path="/"):
    """The host's numbers as seen from the container (/proc is the host's without lxcfs)."""
    import glob
    import shutil
    import time

    def cpu_times():
        with open("/proc/stat") as f:
            nums = [int(x) for x in f.readline().split()[1:]]
        return nums[3] + nums[4], sum(nums)  # idle + iowait, total

    idle1, total1 = cpu_times()
    time.sleep(0.25)
    idle2, total2 = cpu_times()
    with open("/proc/meminfo") as f:
        mem = {k: int(v.split()[0]) for k, v in (line.split(":", 1) for line in f)}
    temps = []
    for zone in glob.glob("/sys/class/thermal/thermal_zone*/temp"):
        with open(zone) as f:
            temps.append(int(f.read()) / 1000)
    with open("/proc/uptime") as f:
        uptime = float(f.read().split()[0])
    disk = shutil.disk_usage(disk_path)
    gb = 1024 ** 3
    return {
        "cpu": round(100 * (1 - (idle2 - idle1) / max(total2 - total1, 1))),
        "ram_used": round((mem["MemTotal"] - mem["MemAvailable"]) / 1024 ** 2, 1),
        "ram_total": round(mem["MemTotal"] / 1024 ** 2, 1),
        "disk_used": round(disk.used / gb),
        "disk_total": round(disk.total / gb),
        "temp": round(max(temps)) if temps and max(temps) > 0 else None,
        "load": round(os.getloadavg()[0], 2),
        "cores": os.cpu_count(),
        "uptime": int(uptime),
    }


class MonitorLight:
    """Devices through Home Bridge (read only); `id` is the monitors' LED strip that sets the UI color."""
    def __init__(self):
        self.url = os.environ.get("FINNIP_BRIDGE_URL", "http://home-bridge:3000").rstrip("/") + "/devices"
        self.id = os.environ.get("MONITOR_LIGHT", "light.leds_monitores")
        self.key = os.environ["BRIDGE_API_KEY"]
        self.http = httpx.AsyncClient(timeout=5)
    async def devices(self):
        resp = await self.http.get(self.url, headers={"Authorization": f"Bearer {self.key}"})
        resp.raise_for_status()
        return resp.json()["devices"]
