"""voice-gateway: the /ws protocol (design.md, decisiones 6 y 9) and the PWA's static files."""
import asyncio
import contextlib
import json
import logging
import os

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles

from . import text as T

log = logging.getLogger("voice_gateway")
MAX_UTTERANCE_BYTES = 16000 * 2 * 60  # 60 s of PCM16 mono 16 kHz
GENERIC_ERROR = "No pude completar la respuesta."


def allowed_user(headers):
    allowed = {u.strip().lower() for u in os.environ.get("ALLOWED_TAILSCALE_USERS", "").split(",") if u.strip()}
    user = (headers.get("tailscale-user-login") or "").strip().lower()
    return bool(user) and user in allowed


class TailscaleOnly(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path != "/health" and not allowed_user(request.headers):
            return PlainTextResponse("Forbidden", status_code=403)
        return await call_next(request)


class Session:
    """One client connection: buffers PCM, runs one reply turn at a time, handles interruptions."""

    def __init__(self, ws, stt, hermes, tts):
        self.ws, self.stt, self.hermes, self.tts = ws, stt, hermes, tts
        self.audio = bytearray()
        self.turn = None          # task streaming the current reply
        self.listening = None     # task transcribing the last utterance
        self.sentences = []       # current reply, index == audio seq
        self.pending_heard = None
        self.lock = asyncio.Lock()

    async def send(self, obj, audio=None):
        async with self.lock:  # keeps an "audio" header and its binary frame together
            await self.ws.send_text(json.dumps(obj, ensure_ascii=False))
            if audio is not None:
                await self.ws.send_bytes(audio)

    async def run(self):
        try:
            while True:
                msg = await self.ws.receive()
                if msg["type"] == "websocket.disconnect":
                    return
                if msg.get("bytes") is not None:
                    if len(self.audio) < MAX_UTTERANCE_BYTES:
                        self.audio += msg["bytes"]
                    continue
                await self.on_control(json.loads(msg.get("text") or "{}"))
        finally:
            for task in (self.listening, self.turn):
                if task:
                    task.cancel()

    async def on_control(self, data):
        kind = data.get("type")
        if kind == "hello":
            await self.send({"type": "ready", "version": 1})
        elif kind == "utterance_end":
            audio, self.audio = bytes(self.audio), bytearray()
            self.listening = asyncio.create_task(self.on_utterance(audio, data))
        elif kind in ("cancel", "interrupt"):
            self.audio = bytearray()
            await self.stop_turn(data if kind == "interrupt" else None)
            await self.send({"type": "done"})

    async def stop_turn(self, played=None):
        if self.turn and not self.turn.done():
            self.turn.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self.turn
        if played and int(played.get("played_seq", 0)) < len(self.sentences):
            self.pending_heard = T.heard_text(self.sentences, int(played.get("played_seq", 0)),
                                              int(played.get("played_ms", 0)))

    async def on_utterance(self, audio, data):
        try:
            transcript = await self.stt.transcribe(audio) if audio else ""
        except Exception:
            log.exception("STT failed")
            await self.send({"type": "error", "message": "No pude entender el audio."})
            return
        barge_in = bool(data.get("barge_in"))
        if barge_in and T.is_echo(transcript, self.sentences):
            await self.send({"type": "resume"})
            return
        await self.stop_turn(data if barge_in else None)
        await self.send({"type": "transcript", "text": transcript})
        if not transcript:
            await self.send({"type": "done"})
            return
        self.turn = asyncio.create_task(self.reply(transcript))

    async def reply(self, user_text):
        prompt = T.with_heard_note(user_text, self.pending_heard)
        self.pending_heard, self.sentences = None, []
        queue = asyncio.Queue()
        synth = []

        def enqueue(sentence):
            task = asyncio.create_task(self.tts.synthesize(sentence))  # synthesis overlaps the LLM stream
            synth.append(task)
            queue.put_nowait((len(self.sentences), sentence, task))
            self.sentences.append(sentence)

        async def produce():
            splitter = T.SentenceSplitter()
            try:
                async for delta in self.hermes.stream(prompt):
                    for sentence in splitter.feed(delta):
                        enqueue(sentence)
                for sentence in splitter.flush():
                    enqueue(sentence)
            finally:
                queue.put_nowait(None)

        async def deliver():
            while (item := await queue.get()) is not None:
                seq, sentence, task = item
                audio = await task
                await self.send({"type": "reply_text", "seq": seq, "text": sentence})
                await self.send({"type": "audio", "seq": seq, "format": "mp3"}, audio)

        try:
            await asyncio.gather(produce(), deliver())
            await self.send({"type": "done"})
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("reply failed")
            await self.send({"type": "error", "message": GENERIC_ERROR})
            await self.send({"type": "done"})
        finally:
            for task in synth:
                task.cancel()


def create_app(stt=None, hermes=None, tts=None):
    if stt is None:
        from .services import EdgeTts, HermesClient, WhisperStt
        stt, hermes, tts = WhisperStt(), HermesClient(), EdgeTts()

    async def ws_endpoint(ws):
        if not allowed_user(ws.headers):
            await ws.close(code=4403)  # before accept: the handshake gets HTTP 403
            return
        await ws.accept()
        await Session(ws, stt, hermes, tts).run()

    async def health(request):
        return JSONResponse({"ok": True})

    routes = [Route("/health", health), WebSocketRoute("/ws", ws_endpoint)]
    static_dir = os.environ.get("STATIC_DIR", "")
    if static_dir and os.path.isdir(static_dir):
        routes.append(Mount("/", StaticFiles(directory=static_dir, html=True)))

    @contextlib.asynccontextmanager
    async def lifespan(app):
        if hasattr(stt, "load"):  # load Whisper before the first utterance, not during it
            await asyncio.to_thread(stt.load)
        yield

    return Starlette(routes=routes, middleware=[Middleware(TailscaleOnly)], lifespan=lifespan)
