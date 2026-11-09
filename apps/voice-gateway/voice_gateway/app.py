"""voice-gateway: the /ws protocol (Session below) and the PWA's static files."""
import asyncio
import contextlib
import json
import logging
import os
import time
from array import array

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles

from . import text as T

log = logging.getLogger("voice_gateway")
MAX_UTTERANCE_BYTES = 16000 * 2 * 60  # 60 s of PCM16 mono 16 kHz
GENERIC_ERROR = "No pude completar la respuesta."
# ponytail: live partials re-transcribe the whole utterance each time (O(n²) CPU on long phrases);
# switch to a streaming STT if phrases get long or the CPU saturates.
PARTIAL_EVERY = 0.3          # seconds between live transcripts
PARTIAL_MIN_BYTES = 9600     # 0.3 s of new audio before another partial
# The client keeps streaming the VAD's end-of-phrase silence (~0.45 s). As soon as the tail goes
# silent the server transcribes right away; at utterance_end that result is the final transcript
# when everything after it is silence (saves the ~0.7-1 s of a fresh transcription).
TAIL_SILENCE_BYTES = 6400    # 0.2 s of silence at the tail triggers an immediate transcription
# ponytail: fixed RMS threshold; a whispered last syllable could read as silence. Tune with real mics.
SILENCE_RMS = 400
DUPLICATE_WINDOW = 5.0       # seconds in which an identical transcript is dropped
# A phrase that arrives before Finnip has said anything continues the previous one (the user paused
# mid-sentence): the pending reply is cancelled and both parts go to Hermes as one message.
MERGE_WINDOW = 8.0           # seconds after the previous phrase in which a continuation is merged


def allowed_user(headers):
    allowed = {u.strip().lower() for u in os.environ.get("ALLOWED_TAILSCALE_USERS", "").split(",") if u.strip()}
    user = (headers.get("tailscale-user-login") or "").strip().lower()
    return bool(user) and user in allowed


def is_silent(pcm16):
    samples = array("h", pcm16[: len(pcm16) // 2 * 2])
    return not samples or (sum(x * x for x in samples) / len(samples)) ** 0.5 < SILENCE_RMS


class TailscaleOnly(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path != "/health" and not allowed_user(request.headers):
            return PlainTextResponse("Forbidden", status_code=403)
        return await call_next(request)


class Session:
    """One client connection: buffers PCM, runs one reply turn at a time, handles interruptions."""

    def __init__(self, ws, stt, hermes, tts, recent=None, stats=None, theme=None, calendar=None):
        self.ws, self.stt, self.hermes, self.tts = ws, stt, hermes, tts
        self.stats = stats        # async () -> host numbers, or None
        self.calendar = calendar  # ICloudCalendar-like (async events()), or None
        self.theme = theme if theme is not None else {}  # shared {"rgb": [r, g, b]} of the monitors
        self.audio = bytearray()
        self.turn = None          # task streaming the current reply
        self.listening = None     # task transcribing the last utterance
        self.partials = None      # task sending live transcripts while the user speaks
        self.partial = ("", 0)    # last live transcript and how many audio bytes it covered
        self.partial_job = None   # (task, bytes covered) of the transcription in flight
        # Shared by every connection: two open clients hearing the same phrase must not both send it.
        self.recent = recent if recent is not None else {"text": "", "at": 0.0}
        self.sentences = []       # current reply, index == audio seq
        self.pending_heard = None
        self.user_text, self.user_at = "", 0.0  # last phrase sent to Hermes
        self.spoke = False        # the current reply already sent audio
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
            for task in (self.listening, self.turn, self.partials):
                if task:
                    task.cancel()

    def stop_partials(self):
        if self.partials:
            self.partials.cancel()
            self.partials = None

    async def live_partials(self):
        covered, last = 0, 0.0
        while True:
            await asyncio.sleep(0.1)
            size = len(self.audio)
            new = bytes(self.audio[covered:size])
            if not new or is_silent(new):
                continue  # nothing spoken since the last transcription
            tail_silent = size >= TAIL_SILENCE_BYTES and is_silent(self.audio[size - TAIL_SILENCE_BYTES:size])
            due = len(new) >= PARTIAL_MIN_BYTES and time.monotonic() - last >= PARTIAL_EVERY
            if not (tail_silent or due):
                continue
            job = asyncio.create_task(self.stt.transcribe(bytes(self.audio[:size])))
            self.partial_job = (job, size)
            text = await asyncio.shield(job)  # utterance_end may still want this result
            self.partial_job = None
            covered, last = size, time.monotonic()
            self.partial = (text, size)
            if text:
                await self.send({"type": "partial", "text": text})

    async def final_from_partials(self, audio):
        """A live transcript that already covers everything but trailing silence, else None."""
        job = self.partial_job
        if job and is_silent(audio[job[1]:]):
            with contextlib.suppress(Exception):
                return await job[0]
        text, covered = self.partial
        if text and is_silent(audio[covered:]):
            return text
        return None

    async def on_control(self, data):
        kind = data.get("type")
        if kind == "hello":
            await self.send({"type": "ready", "version": 1})
            if self.theme.get("rgb"):
                await self.send({"type": "theme", "rgb": self.theme["rgb"]})
        elif kind == "utterance_start":
            self.stop_partials()
            self.audio, self.partial, self.partial_job = bytearray(), ("", 0), None
            self.partials = asyncio.create_task(self.live_partials())
        elif kind == "utterance_abort":
            self.stop_partials()
            self.audio = bytearray()
        elif kind == "utterance_end":
            self.stop_partials()
            audio, self.audio = bytes(self.audio), bytearray()
            self.listening = asyncio.create_task(self.on_utterance(audio, data, reuse=True))
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

    async def on_utterance(self, audio, data, reuse=False):
        try:
            ready = await self.final_from_partials(audio) if reuse else None
            self.partial, self.partial_job = ("", 0), None
            transcript = ready if ready is not None else (await self.stt.transcribe(audio) if audio else "")
        except Exception:
            log.exception("STT failed")
            await self.send({"type": "error", "message": "No pude entender el audio."})
            return
        if data.get("wake"):  # standby: only a phrase that starts with "Finnip" counts
            rest = T.after_wake_word(transcript)
            if rest is None:
                await self.send({"type": "transcript", "text": ""})
                return
            await self.send({"type": "wake"})
            if not rest:
                return
            transcript = rest
        barge_in = bool(data.get("barge_in"))
        if barge_in and T.is_echo(transcript, self.sentences):
            await self.send({"type": "resume"})
            return
        busy = self.turn is not None and not self.turn.done()
        if busy and not barge_in and (not transcript or (self.spoke and T.is_echo(transcript, self.sentences))):
            # Noise, the chime or Finnip's own voice while a reply runs: never cancel the reply for it.
            await self.send({"type": "transcript", "text": ""})
            return
        now = time.monotonic()
        if transcript and transcript == self.recent["text"] and now - self.recent["at"] < DUPLICATE_WINDOW:
            await self.send({"type": "done"})  # same phrase again (duplicated client), Hermes would queue it
            return
        self.recent.update(text=transcript, at=now)
        merge = (bool(transcript) and not barge_in and not self.spoke and self.turn is not None
                 and not self.turn.done() and now - self.user_at < MERGE_WINDOW)
        await self.stop_turn(data if barge_in else None)
        if merge:
            transcript = f"{self.user_text} {transcript}"
        await self.send({"type": "transcript", "text": transcript, **({"merged": True} if merge else {})})
        if not transcript:
            await self.send({"type": "done"})
            return
        self.user_text, self.user_at = transcript, now
        self.turn = asyncio.create_task(self.reply(transcript))

    async def reply(self, user_text):
        prompt = T.with_heard_note(user_text, self.pending_heard)
        self.pending_heard, self.sentences, self.spoke = None, [], False
        if self.stats and T.wants_stats(user_text):
            try:
                stats = await self.stats()
                await self.send({"type": "stats", **stats})
                prompt = T.stats_note(stats, prompt)
            except Exception:
                log.exception("host stats failed")  # Finnip can still measure them with its tools
        if self.calendar and T.wants_reminders(user_text):
            try:
                items = T.calendar_items(await self.calendar.events())
                await self.send({"type": "reminders", "items": items})  # on screen before the voice arrives
                prompt = T.reminders_note(items, prompt)
            except Exception:
                log.exception("calendar failed")  # Finnip can still list them with its tools
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
                self.spoke = True
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


THEME_POLL = 1.0  # seconds between reads of the devices: monitor color + action cards (local HTTP, cheap)


def create_app(stt=None, hermes=None, tts=None, stats=None, monitor=None, calendar=None):
    if stt is None:
        from .services import EdgeTts, HermesClient, ICloudCalendar, MonitorLight, ParakeetStt, host_stats
        stt, hermes, tts = ParakeetStt(), HermesClient(), EdgeTts()
        disk = os.environ.get("STATIC_DIR") or "/"
        stats = lambda: asyncio.to_thread(host_stats, disk)  # noqa: E731
        monitor = MonitorLight() if os.environ.get("BRIDGE_API_KEY") else None
        plugin = os.environ.get("CALENDAR_PLUGIN", "")
        calendar = ICloudCalendar(plugin) if plugin and os.path.exists(plugin) and os.environ.get("CALDAV_CALENDAR_URL") else None

    recent = {"text": "", "at": 0.0}
    theme = {}        # last color the monitors had while on: kept when they turn off
    sessions = set()

    seen = {}         # device id -> (state, brightness, rgb) from the previous poll
    async def broadcast(obj):
        for session in list(sessions):
            with contextlib.suppress(Exception):
                await session.send(obj)
    async def follow_monitors():
        while True:
            try:
                for device in await monitor.devices():
                    on = device.get("state") == "on"
                    rgb = device.get("rgb_color")
                    if device["id"] == monitor.id and on and rgb and rgb != theme.get("rgb"):
                        theme["rgb"] = rgb
                        await broadcast({"type": "theme", "rgb": rgb})
                    key = (device.get("state"), device.get("brightness"), rgb)
                    # A change since the last poll (not the first sight) becomes an action card in the UI.
                    if device["id"] in seen and seen[device["id"]] != key:
                        name = "Monitores" if device["id"] == monitor.id else device.get("name", "")
                        await broadcast({"type": "device", "id": device["id"], "name": name, "on": on,
                                         "brightness": device.get("brightness"), "rgb": rgb})
                    seen[device["id"]] = key
            except Exception as err:
                log.warning("devices: %s", err)
            await asyncio.sleep(THEME_POLL)
    async def ws_endpoint(ws):
        if not allowed_user(ws.headers):
            await ws.close(code=4403)  # before accept: the handshake gets HTTP 403
            return
        await ws.accept()
        session = Session(ws, stt, hermes, tts, recent, stats, theme, calendar)
        sessions.add(session)
        try:
            await session.run()
        finally:
            sessions.discard(session)

    async def health(request):
        return JSONResponse({"ok": True})

    routes = [Route("/health", health), WebSocketRoute("/ws", ws_endpoint)]
    static_dir = os.environ.get("STATIC_DIR", "")
    if static_dir and os.path.isdir(static_dir):
        routes.append(Mount("/", StaticFiles(directory=static_dir, html=True)))

    @contextlib.asynccontextmanager
    async def lifespan(app):
        if hasattr(stt, "load"):  # load the STT model before the first utterance, not during it
            await asyncio.to_thread(stt.load)
        poller = asyncio.create_task(follow_monitors()) if monitor else None
        yield
        if poller:
            poller.cancel()

    # gzip: the VAD's onnxruntime wasm goes from ~15 MB to ~4 MB, which matters over a Tailscale relay.
    middleware = [Middleware(TailscaleOnly), Middleware(GZipMiddleware, minimum_size=1024)]
    return Starlette(routes=routes, middleware=middleware, lifespan=lifespan)
