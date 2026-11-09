import asyncio
import json
import os
import unittest
from unittest import mock

from starlette.testclient import TestClient

from voice_gateway.app import create_app

USER = {"Tailscale-User-Login": "david@example.com"}


class FakeStt:
    async def transcribe(self, pcm16):
        return pcm16.decode()  # tests send the "transcript" as the audio bytes


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
        self.hermes = FakeHermes()
        self.client = TestClient(create_app(FakeStt(), self.hermes, FakeTts()))

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

    def test_silence_gives_empty_transcript_and_done(self):
        with self.client.websocket_connect("/ws", headers=USER) as ws:
            ws.send_json({"type": "utterance_end"})
            self.assertEqual(self.receive_until(ws, "done"), [{"type": "transcript", "text": ""}, {"type": "done"}])
        self.assertEqual(self.hermes.prompts, [])


if __name__ == "__main__":
    unittest.main()
