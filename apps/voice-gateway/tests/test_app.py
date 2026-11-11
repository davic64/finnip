import asyncio
import json
import os
import unittest
from unittest import mock

from starlette.testclient import TestClient

from voice_gateway.app import create_app

USER = {"Tailscale-User-Login": "david@example.com"}


class FakeStt:
    def __init__(self):
        self.calls = 0

    async def transcribe(self, pcm16):
        self.calls += 1
        return pcm16.decode().strip("\x00")  # tests send the "transcript" as the audio bytes; zeros = silence


class FakeHermes:
    def __init__(self):
        self.prompts, self.replies, self.closed = [], [], 0

    async def stream(self, text):
        self.prompts.append(text)
        deltas, hang = self.replies.pop(0)
        try:
            for d in deltas:
                yield d
            if hang:
                await asyncio.Event().wait()  # an endless reply, to be cancelled
        finally:
            self.closed += 1


class FakeVoice:
    """Voiceprint stand-in: the "embedding" is the phrase itself; scores by phrase, 0.9 by default."""
    threshold = 0.5

    def __init__(self, scores=None):
        self.enrolled, self.scores, self.saved = scores is not None, scores or {}, None

    async def embed(self, pcm16):
        return pcm16.decode().strip("\x00") or None

    def score(self, embedding):
        return self.scores.get(embedding, 0.9)

    def save(self, embeddings):
        self.saved, self.enrolled = embeddings, True


class FakeTts:
    async def synthesize(self, text):
        return f"mp3:{text}".encode()


@mock.patch.dict(os.environ, {"ALLOWED_TAILSCALE_USERS": "david@example.com"})
class GatewayTest(unittest.TestCase):
    def setUp(self):
        self.hermes, self.stt = FakeHermes(), FakeStt()
        self.client = TestClient(create_app(self.stt, self.hermes, FakeTts()))

    def say(self, ws, text, **extra):
        ws.send_bytes(text.encode())
        ws.send_json({"type": "utterance_end", **extra})

    def receive_until(self, ws, kind):
        got = []
        while True:
            msg = ws.receive()
            item = msg.get("bytes") if msg.get("bytes") is not None else json.loads(msg["text"])
            got.append(item)
            if isinstance(item, dict) and item["type"] == kind:
                return got

    def test_health_is_public_but_the_rest_needs_an_allowed_user(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(self.client.get("/").status_code, 403)
        self.assertEqual(self.client.get("/", headers={"Tailscale-User-Login": "otro@example.com"}).status_code, 403)
        with self.assertRaises(Exception):
            with self.client.websocket_connect("/ws") as ws:
                ws.receive_json()

    def test_full_turn_streams_sentences_in_order(self):
        self.hermes.replies.append((["Hola, se", "ñor. Son las", " diez."], False))
        with self.client.websocket_connect("/ws", headers=USER) as ws:
            ws.send_json({"type": "hello", "client": "pwa", "version": 1})
            self.assertEqual(ws.receive_json(), {"type": "ready", "version": 1})
            self.say(ws, "qué hora es")
            got = self.receive_until(ws, "done")
        self.assertEqual(got, [
            {"type": "transcript", "text": "qué hora es"},
            {"type": "reply_text", "seq": 0, "text": "Hola, señor."},
            {"type": "audio", "seq": 0, "format": "mp3"}, b"mp3:Hola, se\xc3\xb1or.",
            {"type": "reply_text", "seq": 1, "text": "Son las diez."},
            {"type": "audio", "seq": 1, "format": "mp3"}, b"mp3:Son las diez.",
            {"type": "done"},
        ])
        self.assertEqual(self.hermes.prompts, ["qué hora es"])

    def test_interrupt_stops_hermes_and_next_turn_knows_what_was_heard(self):
        self.hermes.replies += [(["Uno. Dos. "], True), (["Era el dos."], False)]
        with self.client.websocket_connect("/ws", headers=USER) as ws:
            self.say(ws, "dime los pendientes")
            got = self.receive_until(ws, "audio")
            got += [ws.receive_bytes()]
            got += self.receive_until(ws, "audio")
            ws.send_json({"type": "interrupt", "played_seq": 1, "played_ms": 0})
            self.receive_until(ws, "done")
            self.say(ws, "cuál era el segundo")
            self.receive_until(ws, "done")
        self.assertEqual(self.hermes.closed, 2)
        self.assertIn('solo alcanzó a oír: "Uno."', self.hermes.prompts[1])
        self.assertTrue(self.hermes.prompts[1].endswith("cuál era el segundo"))

    def test_barge_in_with_own_voice_resumes(self):
        self.hermes.replies.append((["Las luces de la sala están apagadas. "], True))
        with self.client.websocket_connect("/ws", headers=USER) as ws:
            self.say(ws, "estado de la casa")
            self.receive_until(ws, "audio")
            ws.receive_bytes()
            self.say(ws, "luces de la sala estan apagadas", barge_in=True, played_seq=0, played_ms=500)
            self.assertEqual(ws.receive_json(), {"type": "resume"})
            ws.send_json({"type": "cancel"})
            self.receive_until(ws, "done")
        self.assertEqual(self.hermes.prompts, ["estado de la casa"])

    def test_finnip_para_stops_the_reply_without_asking_hermes(self):
        self.hermes.replies.append((["Hoy tienes tres reuniones. "], True))
        with self.client.websocket_connect("/ws", headers=USER) as ws:
            self.say(ws, "mi agenda")
            self.receive_until(ws, "audio")
            ws.receive_bytes()
            self.say(ws, "Finnip, para", wake=True, barge_in=True, played_seq=0, played_ms=300)
            got = self.receive_until(ws, "transcript")
        self.assertIn({"type": "wake"}, got)
        self.assertEqual(got[-1], {"type": "transcript", "text": ""})
        self.assertEqual(self.hermes.closed, 1)  # the reply was cancelled
        self.assertEqual(self.hermes.prompts, ["mi agenda"])

    def test_orders_said_over_its_own_voice_get_through(self):
        for ask, said, prompts in (("mi agenda", "tienes tres reuniones cállate", ["mi agenda"]),
                                   ("mi día", "hoy tienes Finnip apaga la lámpara", ["mi día", "apaga la lámpara"])):
            self.hermes.prompts.clear()
            self.hermes.replies[:] = [(["Hoy tienes tres reuniones. "], True), (["Listo. "], False)]
            with self.client.websocket_connect("/ws", headers=USER) as ws:
                self.say(ws, ask)
                self.receive_until(ws, "audio")
                ws.receive_bytes()
                self.say(ws, said, wake=True, barge_in=True, played_seq=0, played_ms=300)
                if len(prompts) == 1:
                    self.receive_until(ws, "transcript")
                else:
                    self.receive_until(ws, "done")
            self.assertEqual(len(self.hermes.prompts), len(prompts), said)
            self.assertTrue(self.hermes.prompts[-1].endswith(prompts[-1]), said)  # a new turn carries what was heard

    def test_a_stop_word_alone_stops_the_reply(self):
        self.hermes.replies.append((["Hoy tienes tres reuniones. "], True))
        with self.client.websocket_connect("/ws", headers=USER) as ws:
            self.say(ws, "mi agenda")
            self.receive_until(ws, "audio")
            ws.receive_bytes()
            self.say(ws, "Espera.", wake=True, barge_in=True, played_seq=0, played_ms=300)
            self.assertEqual(ws.receive_json(), {"type": "transcript", "text": ""})
        self.assertEqual(self.hermes.closed, 1)
        self.assertEqual(self.hermes.prompts, ["mi agenda"])
    def test_own_voice_saying_finnip_does_not_interrupt(self):
        self.hermes.replies.append((["Soy Finnip, su asistente. "], True))
        with self.client.websocket_connect("/ws", headers=USER) as ws:
            self.say(ws, "quién eres")
            self.receive_until(ws, "audio")
            ws.receive_bytes()
            self.say(ws, "soy finnip su asistente", wake=True, barge_in=True, played_seq=0, played_ms=500)
            self.assertEqual(ws.receive_json(), {"type": "transcript", "text": ""})
            ws.send_json({"type": "cancel"})
            self.receive_until(ws, "done")
        self.assertEqual(self.hermes.closed, 1)  # only by the test's cancel

    def test_barge_in_with_real_speech_starts_a_new_turn(self):
        self.hermes.replies += [(["Hoy tienes tres reuniones. "], True), (["Listo, señor."], False)]
        with self.client.websocket_connect("/ws", headers=USER) as ws:
            self.say(ws, "mi agenda")
            self.receive_until(ws, "audio")
            ws.receive_bytes()
            self.say(ws, "no espera, apaga la lámpara", barge_in=True, played_seq=0, played_ms=350)
            got = self.receive_until(ws, "done")
        self.assertIn({"type": "transcript", "text": "no espera, apaga la lámpara"}, got)
        self.assertIn({"type": "reply_text", "seq": 0, "text": "Listo, señor."}, got)
        self.assertIn('solo alcanzó a oír: "Hoy…"', self.hermes.prompts[1])

    @mock.patch("voice_gateway.app.PARTIAL_EVERY", 0.01)
    @mock.patch("voice_gateway.app.PARTIAL_MIN_BYTES", 1)
    def test_live_partials_while_speaking(self):
        self.hermes.replies.append((["Bien, señor."], False))
        with self.client.websocket_connect("/ws", headers=USER) as ws:
            ws.send_json({"type": "utterance_start"})
            ws.send_bytes("qué onda".encode())
            self.assertEqual(ws.receive_json(), {"type": "partial", "text": "qué onda"})
            ws.send_bytes(" cómo estás".encode())
            self.assertEqual(ws.receive_json(), {"type": "partial", "text": "qué onda cómo estás"})
            ws.send_json({"type": "utterance_end"})
            got = self.receive_until(ws, "done")
        self.assertEqual(got[0], {"type": "transcript", "text": "qué onda cómo estás"})
        self.assertEqual(self.hermes.prompts, ["qué onda cómo estás"])
        self.assertEqual(self.stt.calls, 2)  # the last partial covered everything: no final re-transcription

    def test_identical_phrase_right_after_is_dropped(self):
        self.hermes.replies.append((["Bien."], False))
        with self.client.websocket_connect("/ws", headers=USER) as ws:
            self.say(ws, "qué onda")
            self.receive_until(ws, "done")
            self.say(ws, "qué onda")
            self.assertEqual(ws.receive_json(), {"type": "done"})
        self.assertEqual(self.hermes.prompts, ["qué onda"])

    def test_two_open_clients_hearing_the_same_phrase_send_it_once(self):
        self.hermes.replies.append((["Bien."], False))
        with self.client.websocket_connect("/ws", headers=USER) as mac, \
                self.client.websocket_connect("/ws", headers=USER) as iphone:
            self.say(mac, "hola finnip")
            self.receive_until(mac, "done")
            self.say(iphone, "hola finnip")
            self.assertEqual(iphone.receive_json(), {"type": "done"})
        self.assertEqual(self.hermes.prompts, ["hola finnip"])

    def test_tail_silence_is_transcribed_at_once_and_reused(self):
        self.hermes.replies.append((["Hola, señor."], False))
        with self.client.websocket_connect("/ws", headers=USER) as ws:
            ws.send_json({"type": "utterance_start"})
            ws.send_bytes("hola finnip".encode() + bytes(6400))  # speech, then 0.2 s of silence
            self.assertEqual(ws.receive_json(), {"type": "partial", "text": "hola finnip"})
            ws.send_bytes(bytes(6400))  # the rest of the VAD's end-of-phrase silence
            ws.send_json({"type": "utterance_end"})
            got = self.receive_until(ws, "done")
        self.assertEqual(got[0], {"type": "transcript", "text": "hola finnip"})
        self.assertEqual(self.stt.calls, 1)  # the silence-triggered partial was the final transcript

    def test_pause_mid_sentence_merges_both_parts(self):
        self.hermes.replies += [([], True), (["Son las diez, señor."], False)]  # 1st reply still thinking
        with self.client.websocket_connect("/ws", headers=USER) as ws:
            self.say(ws, "oye, quería preguntarte")
            self.assertEqual(ws.receive_json(), {"type": "transcript", "text": "oye, quería preguntarte"})
            self.say(ws, "qué hora es")
            got = self.receive_until(ws, "done")
        self.assertEqual(got[0], {"type": "transcript", "text": "oye, quería preguntarte qué hora es", "merged": True})
        self.assertEqual(self.hermes.prompts[-1], "oye, quería preguntarte qué hora es")
        self.assertEqual(self.hermes.closed, 2)  # the half question was cancelled

    def test_no_merge_once_finnip_started_talking(self):
        self.hermes.replies += [(["Claro. "], True), (["Listo."], False)]
        with self.client.websocket_connect("/ws", headers=USER) as ws:
            self.say(ws, "ayúdame con algo")
            self.receive_until(ws, "audio")
            ws.receive_bytes()
            self.say(ws, "apaga la lámpara")
            got = self.receive_until(ws, "done")
        self.assertIn({"type": "transcript", "text": "apaga la lámpara"}, got)

    def test_aborted_utterance_is_dropped(self):
        with self.client.websocket_connect("/ws", headers=USER) as ws:
            ws.send_json({"type": "utterance_start"})
            ws.send_bytes(b"tos")
            ws.send_json({"type": "utterance_abort"})
            ws.send_json({"type": "utterance_end"})
            self.assertEqual(self.receive_until(ws, "done"), [{"type": "transcript", "text": ""}, {"type": "done"}])

    def test_silence_gives_empty_transcript_and_done(self):
        with self.client.websocket_connect("/ws", headers=USER) as ws:
            ws.send_json({"type": "utterance_end"})
            self.assertEqual(self.receive_until(ws, "done"), [{"type": "transcript", "text": ""}, {"type": "done"}])
        self.assertEqual(self.hermes.prompts, [])

    def test_noise_or_echo_while_replying_does_not_cancel_the_reply(self):
        self.hermes.replies.append((["Hola, señor. "], True))
        with self.client.websocket_connect("/ws", headers=USER) as ws:
            self.say(ws, "platícame de ti")
            self.receive_until(ws, "audio")
            ws.send_json({"type": "utterance_end"})  # empty: a cough or the chime
            self.assertEqual(self.receive_until(ws, "transcript")[-1], {"type": "transcript", "text": ""})
            self.say(ws, "hola señor")  # Finnip heard through the speakers
            self.assertEqual(self.receive_until(ws, "transcript")[-1], {"type": "transcript", "text": ""})
            self.assertEqual(self.hermes.closed, 0)
            self.assertEqual(len(self.hermes.prompts), 1)

    def test_standby_utterances_get_no_live_transcripts(self):
        with self.client.websocket_connect("/ws", headers=USER) as ws:
            ws.send_json({"type": "utterance_start", "wake": True})
            ws.send_bytes(b"\x10\x27" * 16000)  # a second of loud audio
            ws.send_json({"type": "utterance_end", "wake": True})
            self.assertEqual(ws.receive_json(), {"type": "transcript", "text": ""})
        self.assertEqual(self.stt.calls, 1)  # one transcription, no partials

    def test_standby_only_wakes_up_with_finnip(self):
        self.hermes.replies.append((["Listo."], False))
        with self.client.websocket_connect("/ws", headers=USER) as ws:
            self.say(ws, "y qué tal el partido", wake=True)
            self.assertEqual(ws.receive_json(), {"type": "transcript", "text": ""})
            self.say(ws, "Finny, apaga la lámpara", wake=True)
            got = self.receive_until(ws, "done")
        self.assertEqual(got[0], {"type": "wake"})
        self.assertIn({"type": "transcript", "text": "apaga la lámpara"}, got)
        self.assertEqual(self.hermes.prompts, ["apaga la lámpara"])

    def test_a_voice_that_is_not_the_user_is_ignored(self):
        voice = FakeVoice({"León es una película argentina": 0.1})
        client = TestClient(create_app(self.stt, self.hermes, FakeTts(), voice=voice))
        self.hermes.replies.append((["Hola."], False))
        with client.websocket_connect("/ws", headers=USER) as ws:
            self.say(ws, "León es una película argentina")
            self.assertEqual(ws.receive_json(), {"type": "transcript", "text": ""})
            self.say(ws, "hola")
            self.receive_until(ws, "done")
        self.assertEqual(self.hermes.prompts, ["hola"])

    def test_learn_my_voice_shows_each_phrase_and_saves_the_voiceprint(self):
        from voice_gateway.voiceprint import ENROLL_PHRASES

        voice = FakeVoice()  # not enrolled yet
        client = TestClient(create_app(self.stt, self.hermes, FakeTts(), voice=voice))
        with client.websocket_connect("/ws", headers=USER) as ws:
            self.say(ws, "Finnip, aprende mi voz", wake=True)
            got = self.receive_until(ws, "done")  # the spoken instructions end the turn
            self.assertIn({"type": "enroll", "step": 1, "total": 5, "text": ENROLL_PHRASES[0]}, got)
            for step, phrase in enumerate(ENROLL_PHRASES, 1):
                self.say(ws, phrase, wake=True)  # standby: no "Finnip" needed while enrolling
                self.assertEqual(ws.receive_json(), {"type": "transcript", "text": ""})
                if step < 5:
                    self.assertEqual(ws.receive_json()["step"], step + 1)
            self.assertEqual(ws.receive_json(), {"type": "enroll", "done": True})
            self.receive_until(ws, "done")
        self.assertEqual(voice.saved, ENROLL_PHRASES)
        self.assertEqual(self.hermes.prompts, [])  # none of it went to Hermes

    def test_panel_saves_routines_for_the_plugin(self):
        import tempfile
        from voice_gateway import app as gateway

        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(gateway, "ROUTINES_FILE", os.path.join(tmp, "routines.json")):
            client = TestClient(create_app(self.stt, self.hermes, FakeTts()))
            self.assertEqual(client.get("/api/routines").status_code, 403)  # Tailscale user only
            self.assertEqual(client.get("/api/routines", headers=USER).json(), {"routines": []})
            home = {"phrase": " Despierta, ya llegó papá ", "reply": "Bienvenido a casa, señor.", "music": "rock"}
            saved = client.put("/api/routines", json={"routines": [home]}, headers=USER).json()["routines"]
            self.assertEqual(saved, [{"phrase": "Despierta, ya llegó papá", "reply": "Bienvenido a casa, señor.",
                                      "music": "rock", "mode": "", "steps": []}])
            lamp = {"device": "light.lampara", "action": "color", "params": {"rgb": [255, 0, 0], "brightness": 60}}
            with_steps = client.put("/api/routines", json={"routines": [{**home, "steps": [lamp]}]}, headers=USER)
            self.assertEqual(with_steps.json()["routines"][0]["steps"], [lamp])
            saved = with_steps.json()["routines"]
            for bad_step in ({"device": "../x", "action": "on"}, {"device": "light.lampara", "action": "command"}):
                bad = client.put("/api/routines", json={"routines": [{**home, "steps": [bad_step]}]}, headers=USER)
                self.assertEqual(bad.status_code, 400)
            self.assertEqual(client.get("/api/routines", headers=USER).json()["routines"], saved)
            bad = client.put("/api/routines", json={"routines": [{"phrase": ""}]}, headers=USER)
            self.assertEqual(bad.status_code, 400)
            form = client.put("/api/routines", content=b"routines=x", headers={**USER, "content-type": "text/plain"})
            self.assertEqual(form.status_code, 415)

    def test_panel_reaches_only_devices_and_modes_on_home_bridge(self):
        asked = []

        async def bridge(method, path, body=None):
            asked.append((method, path, body))
            return 200, {"ok": True}

        client = TestClient(create_app(self.stt, self.hermes, FakeTts(), bridge=bridge))
        client.get("/api/modes", headers=USER)
        client.put("/api/modes/calido", json={"steps": []}, headers=USER)
        client.delete("/api/modes/calido", headers=USER)
        self.assertEqual(client.get("/api/modes/..%2Fdevices", headers=USER).status_code, 404)
        self.assertEqual(client.get("/api/modes/Calido!", headers=USER).status_code, 400)
        self.assertEqual(client.post("/api/devices", headers=USER).status_code, 405)
        self.assertEqual(asked, [("GET", "/modes", None), ("PUT", "/modes/calido", {"steps": []}),
                                 ("DELETE", "/modes/calido", None)])

    def test_a_routine_is_answered_word_for_word_without_hermes(self):
        class FakeRoutines:
            ran = []

            async def find(self, text):
                return {"phrase": "despierta ya llegó papá"} if "papá" in text else None

            async def run(self, item):
                self.ran.append(item["phrase"])
                return "Bienvenido a casa, señor.", []

        routines = FakeRoutines()
        client = TestClient(create_app(self.stt, self.hermes, FakeTts(), routines=routines))
        with client.websocket_connect("/ws", headers=USER) as ws:
            self.say(ws, "Finnip, despierta, ya llegó papá", wake=True)
            got = self.receive_until(ws, "done")
        self.assertIn({"type": "reply_text", "seq": 0, "text": "Bienvenido a casa, señor."}, got)
        self.assertEqual((routines.ran, self.hermes.prompts), (["despierta ya llegó papá"], []))

    def test_low_battery_is_announced(self):
        client = TestClient(create_app(self.stt, self.hermes, FakeTts()))
        with client.websocket_connect("/ws", headers=USER) as ws:
            ws.send_json({"type": "battery", "level": 10})
            got = self.receive_until(ws, "done")
            ws.send_json({"type": "battery", "level": "x"})  # ignored
        self.assertIn({"type": "announce", "text": "Me queda 10 % de pila, señor. Póngame a cargar, por favor."}, got)

    def test_stats_asked_from_the_phone_show_on_the_desktop(self):
        stats = {"cpu": 12, "ram_used": 2.9, "ram_total": 7.6, "disk_used": 27, "disk_total": 225,
                 "temp": 37, "load": 0.34, "cores": 4, "uptime": 90000}

        async def read_stats():
            return stats

        client = TestClient(create_app(self.stt, self.hermes, FakeTts(), stats=read_stats))
        self.hermes.replies.append((["Todo bien."], False))
        with client.websocket_connect("/ws", headers=USER) as desktop, \
                client.websocket_connect("/ws", headers=USER) as phone:
            desktop.send_json({"type": "hello", "client": "desktop"})
            self.assertEqual(desktop.receive_json()["type"], "ready")
            self.say(phone, "cómo está el servidor")
            got = self.receive_until(phone, "done")
            self.assertEqual(desktop.receive_json(), {"type": "stats", **stats})
        self.assertFalse(any(isinstance(m, dict) and m["type"] == "stats" for m in got))
        self.assertIn("RAM 2.9 de 7.6 GB", self.hermes.prompts[0])  # Finnip still reads them out

    def test_server_question_sends_stats_and_feeds_them_to_hermes(self):
        stats = {"cpu": 12, "ram_used": 2.9, "ram_total": 7.6, "disk_used": 27, "disk_total": 225,
                 "temp": 37, "load": 0.34, "cores": 4, "uptime": 90000}

        async def read_stats():
            return stats

        client = TestClient(create_app(self.stt, self.hermes, FakeTts(), stats=read_stats))
        self.hermes.replies += [(["Todo bien."], False), (["Hola."], False)]
        with client.websocket_connect("/ws", headers=USER) as ws:
            self.say(ws, "cómo está el servidor")
            got = self.receive_until(ws, "done")
            self.assertIn({"type": "stats", **stats}, got)
            self.assertIn("RAM 2.9 de 7.6 GB", self.hermes.prompts[0])
            self.assertTrue(self.hermes.prompts[0].endswith("cómo está el servidor"))
            self.say(ws, "hola")
            got = self.receive_until(ws, "done")
        self.assertFalse(any(isinstance(m, dict) and m["type"] == "stats" for m in got))

    def test_reminders_question_shows_them_before_the_reply(self):
        class FakeCalendar:
            async def events(self, start, end):
                return [{"summary": "Pagar luz", "start": "2030-01-02T09:00:00-06:00", "all_day": False}]

        client = TestClient(create_app(self.stt, self.hermes, FakeTts(), calendar=FakeCalendar()))
        self.hermes.replies += [(["Tiene uno."], False), (["Listo."], False)]
        with client.websocket_connect("/ws", headers=USER) as ws:
            self.say(ws, "qué recordatorios tengo")
            got = self.receive_until(ws, "done")
            panel = [m for m in got if isinstance(m, dict) and m["type"] == "reminders"]
            self.assertEqual(panel, [{"type": "reminders", "title": "Próximos 7 días",
                                     "items": [{"name": "Pagar luz", "when": "mié 2 ene · 09:00", "date": "2030-01-02",
                                                "day": "mié 2 ene", "time": "09:00"}]}])
            self.assertLess(got.index(panel[0]), next(i for i, m in enumerate(got) if isinstance(m, dict) and m["type"] == "audio"))
            self.assertIn("Pagar luz (mié 2 ene · 09:00)", self.hermes.prompts[0])
            self.say(ws, "ponme un recordatorio mañana a las 8")
            got = self.receive_until(ws, "done")
        self.assertFalse(any(isinstance(m, dict) and m["type"] == "reminders" for m in got))

    def test_theme_follows_the_monitors_and_survives_them_turning_off(self):
        class FakeMonitor:
            id = "light.leds_monitores"
            colors = [[20, 60, 255], None]

            async def devices(self):
                rgb = self.colors.pop(0) if self.colors else None
                return [{"id": self.id, "state": "on" if rgb else "off", "rgb_color": rgb}]

        with mock.patch("voice_gateway.app.THEME_POLL", 0.01), \
                TestClient(create_app(self.stt, self.hermes, FakeTts(), monitor=FakeMonitor())) as client:
            import time
            time.sleep(0.1)  # the poller saw the color, then "off"
            with client.websocket_connect("/ws", headers=USER) as ws:
                ws.send_json({"type": "hello", "client": "pwa", "version": 1})
                ws.receive_json()
                self.assertEqual(ws.receive_json(), {"type": "theme", "rgb": [20, 60, 255]})

    def test_device_changes_become_action_cards(self):
        echo = [{"id": "media_player.echo", "domain": "media_player", "state": s, "media_title": "Song", "volume": 20}
                for s in ("idle", "playing")]
        off = {"id": "light.lampara", "name": "Lámpara", "state": "off"}
        on = {"id": "light.lampara", "name": "Lámpara", "state": "on", "brightness": 10, "rgb_color": [255, 0, 0]}

        class FakeMonitor:
            id = "light.leds_monitores"
            polls = [[off, echo[0]]] * 10  # first sight is not a change, so no card for it

            async def devices(self):
                return self.polls.pop(0) if self.polls else [echo[1], on]  # the Echo changes too: no card

        with mock.patch("voice_gateway.app.THEME_POLL", 0.05), \
                TestClient(create_app(self.stt, self.hermes, FakeTts(), monitor=FakeMonitor())) as client:
            with client.websocket_connect("/ws", headers=USER) as ws:
                ws.send_json({"type": "hello", "client": "pwa", "version": 1})
                ws.receive_json()
                got = [ws.receive_json() for _ in range(2)]
        # The Echo starting a song is a now-playing update, not a device card.
        self.assertEqual(got[0]["type"], "now_playing")
        self.assertEqual((got[0]["active"], got[0]["title"], got[0]["volume"]), (True, "Song", 20))
        self.assertEqual(got[1], {"type": "device", "id": "light.lampara", "name": "Lámpara",
                                  "on": True, "brightness": 10, "rgb": [255, 0, 0]})


    def test_model_orders_are_answered_without_hermes_and_saved(self):
        import tempfile
        from pathlib import Path
        from voice_gateway.services import ModelRouter
        plugin = Path(__file__).resolve().parents[2] / "finnip-models" / "__init__.py"
        with tempfile.TemporaryDirectory() as tmp:
            router = ModelRouter(str(plugin), os.path.join(tmp, "model.json"))
            router.plugin.openrouter_models = lambda: [{"id": "z-ai/glm-5.3-prime", "created": 2}]
            client = TestClient(create_app(self.stt, self.hermes, FakeTts(), router=router))
            with client.websocket_connect("/ws", headers=USER) as ws:
                self.say(ws, "usa opus")
                got = self.receive_until(ws, "done")
                spoken = " ".join(m["text"] for m in got if isinstance(m, dict) and m["type"] == "reply_text")
                self.assertIn("Opus de su suscripción", spoken)
                self.assertEqual(router.route(), ("anthropic", "claude-opus-5-5"))
                self.say(ws, "que el normal sea glm")
                self.receive_until(ws, "done")
            self.assertEqual(self.hermes.prompts, [])  # never reached Hermes
            self.assertEqual(router.route(), ("openrouter", "z-ai/glm-5.3-prime"))


class PrinterNoticeTest(unittest.TestCase):
    @mock.patch.dict(os.environ, {"ALLOWED_TAILSCALE_USERS": "david@example.com"})
    def test_printer_notice_is_spoken_and_sent_to_telegram(self):
        class OnePrinterNotice:  # says it on every check: the first one may come before the client
            async def step(self):
                return ["Ya puedes meter el filamento."]
        sent = []
        async def notify(text):
            sent.append(text)
        app = create_app(FakeStt(), FakeHermes(), FakeTts(), printer=OnePrinterNotice(), notify=notify)
        with mock.patch("voice_gateway.app.PRINTER_POLL", 0.05), TestClient(app) as client:
            with client.websocket_connect("/ws", headers=USER) as ws:
                got = GatewayTest.receive_until(None, ws, "done")
        self.assertEqual(got[0], {"type": "announce", "text": "Ya puedes meter el filamento."})
        self.assertIn(b"mp3:Ya puedes meter el filamento.", got)
        self.assertEqual(sent[0], "Ya puedes meter el filamento.")


if __name__ == "__main__":
    unittest.main()
