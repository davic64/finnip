"""voice-gateway: the /ws protocol (Session below) and the PWA's static files."""
import asyncio
import base64
import contextlib
import hmac
import json
import logging
import os
import re
import time
import uuid
from array import array

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles

from . import text as T

log = logging.getLogger("voice_gateway")
MAX_UTTERANCE_BYTES = 16000 * 2 * 60  # 60 s of PCM16 mono 16 kHz
GENERIC_ERROR = "No pude completar la respuesta."
# ponytail: live partials re-transcribe the whole utterance each time (O(n²) CPU on long phrases);
# switch to a streaming STT if phrases get long or the CPU saturates.
PARTIAL_EVERY = 0.3          # seconds between live transcripts
PART_SLUG = re.compile(r"^[a-z0-9_]{1,40}$")  # same rule as the finnip-parts service
PHOTO_TIMEOUT = 15.0         # s for the desktop app to take and send a camera frame
MAX_PHOTO_BYTES = 4 * 1024 * 1024
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
        # /internal/* is called by Hermes inside the Compose network (no Tailscale header); it checks
        # PARTS_API_KEY itself.
        path = request.url.path
        if path != "/health" and not path.startswith("/internal/") and not allowed_user(request.headers):
            return PlainTextResponse("Forbidden", status_code=403)
        return await call_next(request)


class Session:
    """One client connection: buffers PCM, runs one reply turn at a time, handles interruptions."""

    def __init__(self, ws, stt, hermes, tts, recent=None, stats=None, theme=None, calendar=None, router=None):
        self.ws, self.stt, self.hermes, self.tts = ws, stt, hermes, tts
        self.stats = stats        # async () -> host numbers, or None
        self.calendar = calendar  # ICloudCalendar-like (async events()), or None
        self.router = router      # ModelRouter-like (route(), order(), async apply()), or None
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
        self.desktop = False      # the macOS overlay (hello client "desktop"): shows parts, has the camera
        self.hello_at = 0.0
        self.photos = {}          # shared by create_app: photo request id -> future for its reply
        self.part = {"open": False}  # shared by create_app: a 3D part is open on a desktop app
        self.to_desktops = None   # set by create_app: async (event) -> sent to every desktop app
        self.lock = asyncio.Lock()

    async def send(self, obj, audio=None):
        async with self.lock:  # keeps an "audio" header and its binary frame together
            await self.ws.send_text(json.dumps(obj, ensure_ascii=False))
            if audio is not None:
                await self.ws.send_bytes(audio)

    async def announce(self, text):
        """Finnip speaks first (printer notices). Skipped while a reply is running: Telegram has it."""
        if self.turn and not self.turn.done():
            return
        audio = await self.tts.synthesize(text)
        self.sentences = [text]  # so its own voice through the mic is recognized as echo
        await self.send({"type": "announce", "text": text})
        await self.send({"type": "reply_text", "seq": 0, "text": text})
        await self.send({"type": "audio", "seq": 0, "format": "mp3"}, audio)
        await self.send({"type": "done"})

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
            self.desktop = data.get("client") == "desktop"
            self.hello_at = time.monotonic()
            await self.send({"type": "ready", "version": 1})
            if self.theme.get("rgb"):
                await self.send({"type": "theme", "rgb": self.theme["rgb"]})
            if (self.theme.get("playing") or {}).get("active"):
                await self.send(self.theme["playing"])
        elif kind == "part_open":
            if self.desktop:
                self.part["open"] = bool(data.get("open"))
        elif kind == "photo":
            future = self.photos.get(data.get("id"))
            if future and not future.done():
                future.set_result(data)
        elif kind == "utterance_start":
            self.stop_partials()
            self.audio, self.partial, self.partial_job = bytearray(), ("", 0), None
            # Standby: no live transcripts. With music the "phrase" never ends, and re-transcribing all
            # of it every 0.3 s pinned the CPU; one transcription per short window is enough for "Finnip".
            if not data.get("wake"):
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
            await self.send({"type": "done"})  # without it the UI stays in "thinking"
            return
        if data.get("wake"):  # standby, or a barge-in while it speaks: only a phrase with "Finnip" counts
            if data.get("barge_in"):
                # The mic hears the user mixed with Finnip's own voice from the speakers: only the words it
                # did not say count, so "cállate" or "Finnip" said over its voice still get through.
                mine = T.unspoken_words(transcript, self.sentences)
                woke = T.after_wake_word(mine, anywhere=True) if mine else None
                if mine and (T.is_stop(mine) or woke == "" or (woke and T.is_stop(woke))):
                    if woke is not None:
                        await self.send({"type": "wake"})
                    await self.stop_turn(data)  # "cállate", "Finnip", "Finnip, para": it stops and listens
                    await self.send({"type": "transcript", "text": ""})
                    return
                if woke is None:  # its own voice, even saying "Finnip", or noise
                    if mine:
                        log.warning("barge-in without wake word: %r", mine[:80])
                    await self.send({"type": "transcript", "text": ""})
                    return
            rest = T.after_wake_word(transcript)
            if rest is None:  # background audio: "Finnip" may fall in the middle of a window
                rest = T.after_wake_word(transcript, anywhere=True)
            if rest is None:
                if transcript:  # to tune the wake word: what the STT wrote when "Finnip" was not found
                    log.warning("no wake word: %r", transcript[:80])
                await self.send({"type": "transcript", "text": ""})
                return
            await self.send({"type": "wake"})
            if data.get("barge_in") and (not rest or T.is_stop(rest)):
                await self.stop_turn(data)  # "Finnip" / "Finnip, para": it stops talking and listens
                await self.send({"type": "transcript", "text": ""})
                return
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
        view = T.part_view(transcript) if self.part["open"] and transcript and self.to_desktops else None
        if view:  # "vista de arriba", "cierra la pieza": the overlay moves the part, Hermes is not asked
            await self.send({"type": "transcript", "text": transcript})
            log.info("part view %s: %r", view, transcript[:60])  # which phrase moved or closed the part
            await self.to_desktops({"type": "part_view", "view": view})
            await self.send({"type": "done"})
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

    async def model_command(self, user_text):
        """The spoken answer to "usa Opus" / "el normal sea DeepSeek", or None when it is not one."""
        order = self.router.order(user_text) if self.router else None
        if order is None:
            return None
        message, _ = await self.router.apply(order)
        return message

    async def reply(self, user_text):
        local = await self.model_command(user_text)  # answered here, without Hermes
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
                label, start, end = T.agenda_range(user_text)
                items = T.calendar_items(await self.calendar.events(start, end))
                # On screen before the voice arrives.
                await self.send({"type": "reminders", "title": label, "items": items})
                prompt = T.reminders_note(items, prompt, label)
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
                async for delta in (_once(local) if local is not None else self.hermes.stream(prompt)):
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


async def _once(text):
    yield text


THEME_POLL = 1.0  # seconds between reads of the devices: monitor color + action cards (local HTTP, cheap)
PRINTER_POLL = 3.0  # seconds between printer checks (OctoPrint on the Compose network)


def create_app(stt=None, hermes=None, tts=None, stats=None, monitor=None, calendar=None, router=None,
               printer=None, notify=None, parts=None):
    if stt is None:
        from .services import (EdgeTts, HermesClient, ICloudCalendar, ModelRouter, MonitorLight, ParakeetStt,
                               PartsClient, Printer, host_stats, telegram)
        stt, hermes, tts = ParakeetStt(), HermesClient(), EdgeTts()
        disk = os.environ.get("STATIC_DIR") or "/"
        stats = lambda: asyncio.to_thread(host_stats, disk)  # noqa: E731
        monitor = MonitorLight() if os.environ.get("BRIDGE_API_KEY") else None
        plugin = os.environ.get("CALENDAR_PLUGIN", "")
        calendar = ICloudCalendar(plugin) if plugin and os.path.exists(plugin) and os.environ.get("CALDAV_CALENDAR_URL") else None
        models_plugin, state = os.environ.get("MODELS_PLUGIN", ""), os.environ.get("MODEL_STATE", "")
        router = ModelRouter(models_plugin, state) if os.path.exists(models_plugin) and state else None
        hermes.router = router
        printer_plugin = os.environ.get("PRINTER_PLUGIN", "")
        printer = Printer(printer_plugin) if os.path.exists(printer_plugin) and os.environ.get("OCTOPRINT_API_KEY") else None
        notify = telegram if os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID") else None
        parts = PartsClient() if os.environ.get("PARTS_API_KEY") else None

    recent = {"text": "", "at": 0.0}
    theme = {}        # "rgb": last color the monitors had while on; "playing": the speaker's now-playing event
    sessions = set()
    photos = {}       # photo request id -> future, answered by the desktop app's "photo" message
    part = {"open": False}  # a desktop app has a 3D part open (it says so with "part_open")

    seen = {}         # device id -> (state, brightness, rgb) from the previous poll
    async def broadcast(obj):
        for session in list(sessions):
            with contextlib.suppress(Exception):
                await session.send(obj)
    async def follow_monitors():
        while True:
            try:
                for device in await monitor.devices():
                    if device.get("domain") == "media_player":
                        playing = T.now_playing(device)
                        if playing != theme.get("playing"):
                            theme["playing"] = playing
                            await broadcast(playing)
                    on = device.get("state") == "on"
                    rgb = device.get("rgb_color")
                    if device["id"] == monitor.id and on and rgb and rgb != theme.get("rgb"):
                        theme["rgb"] = rgb
                        await broadcast({"type": "theme", "rgb": rgb})
                    key = (device.get("state"), device.get("brightness"), rgb)
                    # A change since the last poll (not the first sight) becomes an action card in the UI.
                    # ponytail: speakers (media_player) get no card; their on/off card would say "Apagado"
                    # on every track change. Add a "now playing" card if wanted.
                    if device["id"] in seen and seen[device["id"]] != key and device.get("domain") != "media_player":
                        name = "Monitores" if device["id"] == monitor.id else device.get("name", "")
                        await broadcast({"type": "device", "id": device["id"], "name": name, "on": on,
                                         "brightness": device.get("brightness"), "rgb": rgb})
                    seen[device["id"]] = key
            except Exception as err:
                log.warning("devices: %s", err)
            await asyncio.sleep(THEME_POLL)
    async def follow_printer():
        while True:
            try:
                for text in await printer.step():
                    for session in list(sessions):
                        with contextlib.suppress(Exception):
                            await session.announce(text)
                    if notify:
                        with contextlib.suppress(Exception):
                            await notify(text)
            except Exception as err:
                log.warning("printer: %s", err)
            await asyncio.sleep(PRINTER_POLL)
    async def ws_endpoint(ws):
        if not allowed_user(ws.headers):
            await ws.close(code=4403)  # before accept: the handshake gets HTTP 403
            return
        await ws.accept()
        session = Session(ws, stt, hermes, tts, recent, stats, theme, calendar, router)
        session.photos = photos
        session.part = part
        session.to_desktops = to_desktops
        sessions.add(session)
        try:
            await session.run()
        finally:
            sessions.discard(session)

    async def health(request):
        return JSONResponse({"ok": True})

    def internal_allowed(request):
        key = os.environ.get("PARTS_API_KEY", "")
        given = request.headers.get("authorization", "")
        return len(key) >= 32 and hmac.compare_digest(given.encode(), f"Bearer {key}".encode())

    async def to_desktops(event):
        for session in desktops():
            with contextlib.suppress(Exception):
                await session.send(event)

    def desktops():
        """Connected desktop apps, the most recent first (a reopened app may leave an old socket behind)."""
        return sorted((s for s in sessions if s.desktop), key=lambda s: s.hello_at, reverse=True)

    async def show_part(request):
        """Hermes (finnip_parts show): the desktop overlay opens this part as a hologram."""
        if not internal_allowed(request):
            return JSONResponse({"error": "No autorizado"}, status_code=401)
        body = await request.json()
        slug, version, size = body.get("slug"), body.get("version"), body.get("size_mm")
        if not isinstance(slug, str) or not PART_SLUG.match(slug) or type(version) is not int or version < 1:
            return JSONResponse({"error": "Pieza inválida"}, status_code=400)
        targets = desktops()
        if not targets:
            return JSONResponse({"error": "La app de escritorio no está conectada"}, status_code=409)
        valid_size = isinstance(size, list) and len(size) == 3 and all(isinstance(v, (int, float)) for v in size)
        event = {"type": "part", "slug": slug, "version": version, "name": str(body.get("name") or slug)[:60],
                 "size_mm": size if valid_size else None, "url": f"/parts/{slug}/v{version}.stl"}
        for session in targets:
            with contextlib.suppress(Exception):
                await session.send(event)
        return JSONResponse({"shown": slug, "version": version})

    async def part_stl(request):
        """The part's STL for the overlay, fetched from finnip-parts (the browser never holds its key)."""
        slug, version = request.path_params["slug"], request.path_params["version"]
        if parts is None or not PART_SLUG.match(slug):
            return PlainTextResponse("Not found", status_code=404)
        try:
            data = await parts.stl(slug, version)
        except LookupError:
            return PlainTextResponse("Not found", status_code=404)
        return Response(data, media_type="model/stl", headers={"Cache-Control": "private, max-age=3600"})

    async def take_photo(request):
        """Hermes (finnip_parts look): one camera frame from the desktop app, as JPEG."""
        if not internal_allowed(request):
            return JSONResponse({"error": "No autorizado"}, status_code=401)
        targets = desktops()
        if not targets:
            return JSONResponse({"error": "La app de escritorio no está conectada"}, status_code=409)
        request_id = uuid.uuid4().hex
        photos[request_id] = asyncio.get_running_loop().create_future()
        try:
            await targets[0].send({"type": "photo_request", "id": request_id})
            reply = await asyncio.wait_for(photos[request_id], PHOTO_TIMEOUT)
        except asyncio.TimeoutError:
            return JSONResponse({"error": "La app de escritorio no mandó la foto a tiempo"}, status_code=504)
        finally:
            photos.pop(request_id, None)
        if reply.get("error"):
            return JSONResponse({"error": str(reply["error"])[:200]}, status_code=502)
        try:
            jpeg = base64.b64decode(reply.get("jpeg") or "", validate=True)
        except ValueError:
            jpeg = b""
        if not jpeg.startswith(b"\xff\xd8") or len(jpeg) > MAX_PHOTO_BYTES:
            return JSONResponse({"error": "La foto llegó dañada"}, status_code=502)
        return Response(jpeg, media_type="image/jpeg")

    routes = [Route("/health", health), WebSocketRoute("/ws", ws_endpoint),
              Route("/internal/part", show_part, methods=["POST"]),
              Route("/internal/photo", take_photo, methods=["POST"]),
              Route("/parts/{slug}/v{version:int}.stl", part_stl)]
    static_dir = os.environ.get("STATIC_DIR", "")
    if static_dir and os.path.isdir(static_dir):
        routes.append(Mount("/", StaticFiles(directory=static_dir, html=True)))

    @contextlib.asynccontextmanager
    async def lifespan(app):
        if hasattr(stt, "load"):  # load the STT model before the first utterance, not during it
            await asyncio.to_thread(stt.load)
        tasks = [asyncio.create_task(f()) for f, on in ((follow_monitors, monitor), (follow_printer, printer)) if on]
        yield
        for task in tasks:
            task.cancel()

    # gzip: the VAD's onnxruntime wasm goes from ~15 MB to ~4 MB, which matters over a Tailscale relay.
    middleware = [Middleware(TailscaleOnly), Middleware(GZipMiddleware, minimum_size=1024)]
    app = Starlette(routes=routes, middleware=middleware, lifespan=lifespan)
    app.state.theme = theme  # shared state, set by tests
    return app
