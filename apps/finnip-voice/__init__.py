import json
import os
import urllib.error
import urllib.request

from agent.tts_provider import TTSProvider

FISH_TTS_URL = "https://api.fish.audio/v1/tts"
DEFAULT_VOICE = "ae74d1059517440aa6e5d2d50598d179"  # "Jarvis", español
DEFAULT_MODEL = "s2.1-pro-free"
OPUS_FORMATS = ("ogg", "opus")
TIMEOUT_SECONDS = 30


def fish_tts(text, voice, model, audio_format):
    """Return the audio bytes Fish Audio synthesizes for text. Errors never include the API key."""
    api_key = os.environ.get("FISH_API_KEY")
    if not api_key:
        raise RuntimeError("FISH_API_KEY no está configurada")

    body = json.dumps({"text": text, "reference_id": voice, "format": audio_format}).encode("utf-8")
    request = urllib.request.Request(
        url=FISH_TTS_URL,
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "model": model},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            audio = response.read()
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace").strip()[:200]
        suffix = f": {detail}" if detail else ""
        raise RuntimeError(f"Fish Audio devolvió HTTP {error.code}{suffix}") from None
    except (urllib.error.URLError, TimeoutError) as error:
        reason = getattr(error, "reason", error)
        raise RuntimeError(f"No se pudo conectar con Fish Audio: {reason}") from None
    if not audio:
        raise RuntimeError("Fish Audio devolvió audio vacío")
    return audio


class FishTTSProvider(TTSProvider):
    @property
    def name(self):
        return "fish"

    @property
    def display_name(self):
        return "Fish Audio"

    def is_available(self):
        return bool(os.environ.get("FISH_API_KEY"))

    def default_voice(self):
        return DEFAULT_VOICE

    @property
    def voice_compatible(self):
        return True

    def synthesize(self, text, output_path, *, voice=None, model=None, speed=None, format="mp3", **extra):
        # Telegram voice bubbles need Ogg/Opus, which Fish returns natively.
        opus = (format or "").lower() in OPUS_FORMATS or output_path.endswith(".ogg")
        audio = fish_tts(text, voice or DEFAULT_VOICE, model or DEFAULT_MODEL, "opus" if opus else "mp3")
        path = os.path.splitext(output_path)[0] + (".ogg" if opus else ".mp3")
        with open(path, "wb") as file:
            file.write(audio)
        return path


def register(ctx):
    ctx.register_tts_provider(FishTTSProvider())
