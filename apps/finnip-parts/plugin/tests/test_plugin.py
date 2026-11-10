import importlib.util
import io
import json
import os
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

spec = importlib.util.spec_from_file_location("finnip_parts", Path(__file__).parent.parent / "__init__.py")
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)

PART = {"slug": "soporte", "name": "Soporte", "versions": [{"version": 1}, {"version": 2}],
        "current": {"version": 2, "size_mm": [40, 20, 5], "code": "cube(1);",
                    "slice": {"material": "PETG", "seconds": 900, "grams": 3.2}}}
READY = {"state": {"text": "Operational", "flags": {"operational": True, "printing": False, "error": False}}}


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@mock.patch.dict(os.environ, {"PARTS_API_KEY": "p" * 32, "OCTOPRINT_API_KEY": "o" * 32})
class PluginTest(unittest.TestCase):
    def call(self, params, routes):
        """routes: (method, url suffix) -> JSON reply, bytes, or an HTTP status to fail with."""
        sent = []

        def urlopen(request, timeout):
            sent.append(request)
            for (method, suffix), reply in routes.items():
                if request.get_method() == method and request.full_url.endswith(suffix):
                    if isinstance(reply, int):
                        raise urllib.error.HTTPError(request.full_url, reply, "x", {}, io.BytesIO(b'{"error": "fallo"}'))
                    return FakeResponse(reply if isinstance(reply, bytes) else json.dumps(reply).encode())
            raise AssertionError(f"unexpected {request.get_method()} {request.full_url}")

        with mock.patch.object(plugin.urllib.request, "urlopen", urlopen):
            return json.loads(plugin.handle(params)), sent

    def test_slugify(self):
        self.assertEqual(plugin.slugify("Soporte del Cargador (v2)"), "soporte_del_cargador_v2")
        self.assertEqual(plugin.slugify("Tapa ñandú"), "tapa_nandu")
        self.assertRaises(ValueError, plugin.slugify, "  ")

    def test_design_posts_the_code_with_the_key(self):
        result, sent = self.call({"action": "design", "name": "Soporte", "code": "cube(10);"},
                                 {("POST", "/parts/soporte/versions"): {"version": 1, "size_mm": [10, 10, 10]}})
        self.assertEqual(result["result"], {"slug": "soporte", "version": 1, "size_mm": [10, 10, 10]})
        self.assertEqual(json.loads(sent[0].data)["code"], "cube(10);")
        self.assertEqual(sent[0].get_header("Authorization"), "Bearer " + "p" * 32)

    def test_service_errors_reach_the_model(self):
        result, _ = self.call({"action": "design", "name": "x", "code": 'import("a.stl");'},
                              {("POST", "/parts/x/versions"): 400})
        self.assertEqual(result, {"success": False, "error": "fallo"})

    def test_slice_uses_the_current_version_and_pla_by_default(self):
        _, sent = self.call({"action": "slice", "name": "Soporte"}, {
            ("GET", "/parts/soporte"): PART, ("POST", "/parts/soporte/versions/2/slice"): {"seconds": 1}})
        self.assertEqual(json.loads(sent[1].data), {"material": "PLA", "settings": {}})

    def test_print_uploads_and_starts(self):
        result, sent = self.call({"action": "print", "name": "Soporte", "confirmed": True}, {
            ("GET", "/parts/soporte"): PART, ("GET", "/api/printer?exclude=sd,temperature"): READY,
            ("GET", "/parts/soporte/v2.gcode"): b"G28\n", ("POST", "/api/files/local"): {"done": True}})
        self.assertEqual(result["result"], {"printing": "Soporte", "version": 2, "material": "PETG", "seconds": 900, "grams": 3.2})
        upload = sent[-1]
        self.assertIn(b'filename="soporte_v2_petg.gcode"', upload.data)
        self.assertIn(b'name="print"\r\n\r\ntrue', upload.data)
        self.assertEqual(upload.get_header("X-api-key"), "o" * 32)

    def test_print_is_refused_without_reaching_octoprint_files(self):
        unsliced = {**PART, "current": {**PART["current"], "slice": None}}
        busy = {"state": {"text": "Printing", "flags": {"operational": True, "printing": True}}}
        cases = [
            ({"confirmed": True}, {("GET", "/parts/soporte"): unsliced}, "no está rebanada"),
            ({}, {("GET", "/parts/soporte"): PART}, "confirmación"),
            ({"confirmed": "sí"}, {("GET", "/parts/soporte"): PART}, "confirmación"),
            ({"confirmed": True}, {("GET", "/parts/soporte"): PART, ("GET", "/api/printer?exclude=sd,temperature"): busy}, "ocupada"),
            ({"confirmed": True}, {("GET", "/parts/soporte"): PART, ("GET", "/api/printer?exclude=sd,temperature"): 409}, "power_on"),
        ]
        for extra, routes, message in cases:
            result, sent = self.call({"action": "print", "name": "Soporte", **extra}, routes)
            self.assertFalse(result["success"], message)
            self.assertIn(message, result["error"])
            self.assertFalse(any("/api/files" in r.full_url or r.full_url.endswith(".gcode") for r in sent), message)

    def test_show_tells_the_gateway(self):
        _, sent = self.call({"action": "show", "name": "soporte", "version": 1}, {
            ("GET", "/parts/soporte?version=1"): {**PART, "current": {**PART["current"], "version": 1}},
            ("POST", "/internal/part"): {}})
        self.assertEqual(json.loads(sent[1].data), {"slug": "soporte", "version": 1, "name": "Soporte", "size_mm": [40, 20, 5]})
        for status, message in ((409, "no está abierta"), (404, "todavía no está disponible")):
            result, _ = self.call({"action": "show", "name": "soporte"}, {
                ("GET", "/parts/soporte"): PART, ("POST", "/internal/part"): status})
            self.assertIn(message, result["error"])

    def test_look_returns_the_photo_as_an_image(self):
        jpeg = b"\xff\xd8\xff\xe0photo"
        result = None
        def urlopen(request, timeout):
            self.assertEqual((request.get_method(), request.full_url), ("POST", "http://voice-gateway:8765/internal/photo"))
            self.assertEqual(request.get_header("Authorization"), "Bearer " + "p" * 32)
            return FakeResponse(jpeg)
        with mock.patch.object(plugin.urllib.request, "urlopen", urlopen):
            result = plugin.handle({"action": "look"})
        self.assertIs(result["_multimodal"], True)
        self.assertIn("aproximado", result["content"][0]["text"])
        self.assertEqual(result["content"][1]["image_url"]["url"], "data:image/jpeg;base64,/9j/4HBob3Rv")

    def test_look_explains_why_there_is_no_photo(self):
        for status, message in ((409, "no está abierta"), (504, "a tiempo"), (502, "fallo")):
            result, _ = self.call({"action": "look"}, {("POST", "/internal/photo"): status})
            self.assertIn(message, result["error"])


if __name__ == "__main__":
    unittest.main()
