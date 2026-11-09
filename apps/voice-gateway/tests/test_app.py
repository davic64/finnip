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

    def test_theme_follows_the_monitors_and_survives_them_turning_off(self):
        class FakeMonitor:
            colors = [[20, 60, 255], None]

            async def rgb(self):
                return self.colors.pop(0) if self.colors else None

        with mock.patch("voice_gateway.app.THEME_POLL", 0.01), \
                TestClient(create_app(self.stt, self.hermes, FakeTts(), monitor=FakeMonitor())) as client:
            import time
            time.sleep(0.1)  # the poller saw the color, then "off"
            with client.websocket_connect("/ws", headers=USER) as ws:
                ws.send_json({"type": "hello", "client": "pwa", "version": 1})
                ws.receive_json()
                self.assertEqual(ws.receive_json(), {"type": "theme", "rgb": [20, 60, 255]})


if __name__ == "__main__":
    unittest.main()
