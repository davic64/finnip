import base64
import os
import threading
import unittest
from unittest import mock

from starlette.testclient import TestClient

from tests.test_app import USER, FakeHermes, FakeStt, FakeTts
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
        # As a context manager the client keeps one event loop for every request and websocket, like the
        # real server; otherwise /internal/photo and the desktop socket would live on different loops.
        self.client = TestClient(create_app(FakeStt(), FakeHermes(), FakeTts(), parts=self.parts)).__enter__()
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


if __name__ == "__main__":
    unittest.main()
