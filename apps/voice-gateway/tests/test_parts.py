import base64
import json
import os
import threading
import unittest
from unittest import mock

from starlette.testclient import TestClient

from tests.test_app import USER, FakeHermes, FakeStt, FakeTts
from voice_gateway import text as T
from voice_gateway.app import create_app

KEY = "p" * 32
AUTH = {"Authorization": f"Bearer {KEY}"}
JPEG = b"\xff\xd8\xff\xe0fake-jpeg"


class FakeParts:
    def __init__(self):
        self.asked = []

    async def stl(self, slug, version):
        self.asked.append((slug, version))
        if slug != "soporte":
            raise LookupError(slug)
        return b"solid finnip"


@mock.patch.dict(os.environ, {"ALLOWED_TAILSCALE_USERS": "david@example.com", "PARTS_API_KEY": KEY})
class PartsGatewayTest(unittest.TestCase):
    def setUp(self):
        self.parts = FakeParts()
        self.hermes = FakeHermes()
        # As a context manager the client keeps one event loop for every request and websocket, like the
        # real server; otherwise /internal/photo and the desktop socket would live on different loops.
        self.client = TestClient(create_app(FakeStt(), self.hermes, FakeTts(), parts=self.parts)).__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def connect(self, client_kind):
        ws = self.client.websocket_connect("/ws", headers=USER).__enter__()
        self.addCleanup(ws.__exit__, None, None, None)
        ws.send_json({"type": "hello", "client": client_kind, "version": 1})
        self.assertEqual(ws.receive_json()["type"], "ready")
        return ws

    def test_stl_is_proxied_only_for_allowed_users_and_valid_names(self):
        response = self.client.get("/parts/soporte/v2.stl", headers=USER)
        self.assertEqual((response.status_code, response.content), (200, b"solid finnip"))
        self.assertEqual(response.headers["content-type"], "model/stl")
        self.assertEqual(self.client.get("/parts/soporte/v2.stl").status_code, 403)  # no Tailscale user
        self.assertEqual(self.client.get("/parts/otra/v1.stl", headers=USER).status_code, 404)
        for bad in ("/parts/..%2F..%2Fetc/v1.stl", "/parts/Soporte/v1.stl", "/parts/soporte/vx.stl"):
            self.assertEqual(self.client.get(bad, headers=USER).status_code, 404, bad)
        self.assertEqual(self.parts.asked, [("soporte", 2), ("otra", 1)])

    def test_internal_routes_need_the_parts_key(self):
        for path in ("/internal/part", "/internal/photo"):
            self.assertEqual(self.client.post(path, json={}).status_code, 401)
            self.assertEqual(self.client.post(path, json={}, headers={"Authorization": "Bearer " + "x" * 32}).status_code, 401)

    def test_show_needs_a_desktop_app_and_reaches_only_it(self):
        body = {"slug": "soporte", "version": 2, "name": "Soporte", "size_mm": [40, 20, 5]}
        self.assertEqual(self.client.post("/internal/part", json=body, headers=AUTH).status_code, 409)
        phone = self.connect("pwa")
        desktop = self.connect("desktop")
        response = self.client.post("/internal/part", json=body, headers=AUTH)
        self.assertEqual(response.json(), {"shown": "soporte", "version": 2})
        self.assertEqual(desktop.receive_json(), {"type": "part", "slug": "soporte", "version": 2, "name": "Soporte",
                                                  "size_mm": [40, 20, 5], "url": "/parts/soporte/v2.stl"})
        phone.send_json({"type": "hello", "client": "pwa"})
        self.assertEqual(phone.receive_json()["type"], "ready")  # the phone got no "part" event before this
        for bad in ({**body, "slug": "../x"}, {**body, "version": "2"}, {**body, "version": 0}):
            self.assertEqual(self.client.post("/internal/part", json=bad, headers=AUTH).status_code, 400)

    def test_project_requests_go_to_the_mac_and_finished_tasks_are_told(self):
        body = {"action": "create", "name": "tienda", "shell": "rm -rf ~"}
        self.assertEqual(self.client.post("/internal/project", json=body, headers=AUTH).status_code, 409)
        self.assertEqual(self.client.post("/internal/project", json={"action": "exec"}, headers=AUTH).status_code, 400)
        self.hermes.replies += [(["Hola."], False), (["Ya quedó la página, señor."], False)]

        def until(ws, kind):
            got = []
            while not (got and isinstance(got[-1], dict) and got[-1]["type"] == kind):
                msg = ws.receive()
                got.append(msg.get("bytes") if msg.get("bytes") is not None else json.loads(msg["text"]))
            return got

        phone, desktop = self.connect("pwa"), self.connect("desktop")
        if True:
            result = {}
            thread = threading.Thread(target=lambda: result.update(
                r=self.client.post("/internal/project", json=body, headers=AUTH)))
            thread.start()
            asked = desktop.receive_json()
            self.assertEqual({k: asked[k] for k in ("type", "action", "name")},
                             {"type": "project_request", "action": "create", "name": "tienda"})
            self.assertNotIn("shell", asked)  # only the known fields reach the Mac
            desktop.send_json({"type": "project_result", "id": asked["id"], "result": {"created": "tienda"}})
            thread.join(10)
            self.assertEqual(result["r"].json(), {"created": "tienda"})
            # The user spoke from the phone last: Claude Code's news is told there.
            phone.send_bytes(b"hola")
            phone.send_json({"type": "utterance_end"})
            until(phone, "done")
            desktop.send_json({"type": "project_done", "name": "tienda", "result": "Hice la página.",
                               "pending": ["npm install"]})
            got = until(phone, "done")
        self.assertIn({"type": "reply_text", "seq": 0, "text": "Ya quedó la página, señor."}, got)
        self.assertIn("npm install", self.hermes.prompts[-1])
        self.assertIn("confirmed true", self.hermes.prompts[-1])

    def test_pointing_at_a_cloud_project_takes_the_capture_on_the_mac(self):
        from voice_gateway import app as gateway

        sent = {}

        class Runner:
            status_code = 200

            def json(self):
                return {"started": "tienda"}

        async def post(self, url, json):
            sent.update(json)
            return Runner()

        desktop = self.connect("desktop")
        body = {"action": "task", "name": "tienda", "request": "hazlo más grande", "where": "cloud", "point": True}
        result = {}
        with mock.patch.object(gateway.httpx.AsyncClient, "post", post):
            thread = threading.Thread(target=lambda: result.update(
                r=self.client.post("/internal/project", json=body, headers=AUTH)))
            thread.start()
            asked = desktop.receive_json()
            self.assertEqual(asked["action"], "capture")
            desktop.send_json({"type": "project_result", "id": asked["id"], "result": {"jpeg": "/9j/", "x": 40, "y": 60}})
            thread.join(10)
        self.assertEqual(result["r"].json(), {"started": "tienda"})
        self.assertEqual((sent["image"], sent["x"], sent["y"], sent["request"]), ("/9j/", 40, 60, "hazlo más grande"))
        self.assertEqual(self.client.post("/internal/project", json={"action": "capture"}, headers=AUTH).status_code, 400)

    def photo(self, answer):
        """Asks for a photo while the desktop app answers with `answer` (or never, if None)."""
        desktop = self.connect("desktop")
        result = {}
        thread = threading.Thread(target=lambda: result.update(r=self.client.post("/internal/photo", headers=AUTH)))
        thread.start()
        request = desktop.receive_json()
        self.assertEqual(request["type"], "photo_request")
        if answer is not None:
            desktop.send_json({"type": "photo", "id": request["id"], **answer})
        thread.join(10)
        return result["r"]

    def test_photo_round_trip(self):
        response = self.photo({"jpeg": base64.b64encode(JPEG).decode()})
        self.assertEqual((response.status_code, response.content), (200, JPEG))
        self.assertEqual(response.headers["content-type"], "image/jpeg")

    def test_photo_errors(self):
        self.assertEqual(self.client.post("/internal/photo", headers=AUTH).status_code, 409)  # no desktop app
        response = self.photo({"error": "Permiso de cámara denegado"})
        self.assertEqual((response.status_code, response.json()["error"]), (502, "Permiso de cámara denegado"))
        self.assertEqual(self.photo({"jpeg": base64.b64encode(b"not a jpeg").decode()}).status_code, 502)
        with mock.patch("voice_gateway.app.PHOTO_TIMEOUT", 0.2):
            self.assertEqual(self.photo(None).status_code, 504)

    def test_view_orders_go_to_the_open_part_without_hermes(self):
        hermes = FakeHermes()
        app = create_app(FakeStt(), hermes, FakeTts(), parts=self.parts)
        with TestClient(app) as client, client.websocket_connect("/ws", headers=USER) as desktop:
            desktop.send_json({"type": "hello", "client": "desktop"})
            desktop.receive_json()
            desktop.send_bytes(b"Vista de arriba.")  # no part open yet: it goes to Hermes
            hermes.replies.append((["Claro."], False))
            desktop.send_json({"type": "utterance_end"})
            got = [desktop.receive_json() for _ in range(2)]
            self.assertEqual(got[0], {"type": "transcript", "text": "Vista de arriba."})
            self.assertEqual(hermes.prompts, ["Vista de arriba."])
            while '"done"' not in (desktop.receive().get("text") or ""):
                pass  # the reply's sentences and audio
            desktop.send_json({"type": "part_open", "open": True})
            desktop.send_bytes("Gírala, por favor.".encode())
            desktop.send_json({"type": "utterance_end"})
            self.assertEqual([desktop.receive_json() for _ in range(3)], [
                {"type": "transcript", "text": "Gírala, por favor."}, {"type": "part_view", "view": "spin"}, {"type": "done"}])
            self.assertEqual(len(hermes.prompts), 1)


class PartViewTextTest(unittest.TestCase):
    def test_orders(self):
        cases = {
            "Vista de arriba.": "top", "Finnip, ponla de frente": "front", "vista lateral": "side",
            "Cierra la pieza.": "close", "quita el holograma": "close", "ciérrala": "close", "Gírala": "spin", "deja de girarla": "still",
            "Más cerca, por favor": "closer", "aléjala": "farther", "Vista inicial": "reset", "desde abajo": "bottom",
            "enséñala de lado": "side",
        }
        for text, view in cases.items():
            self.assertEqual(T.part_view(text), view, text)
        for text in ("Cierra la puerta del garaje", "¿Qué hay arriba en mi agenda?", "Hazla 5 mm más alta",
                     "gira la lámpara a la izquierda", "", "Quítala.", "cierra", "quítale la ranura"):
            self.assertIsNone(T.part_view(text), text)


if __name__ == "__main__":
    unittest.main()
