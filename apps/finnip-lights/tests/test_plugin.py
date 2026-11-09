import importlib.util
import io
import json
import os
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

# The plugin directory name has a hyphen, so load __init__.py by path.
spec = importlib.util.spec_from_file_location("finnip_lights", Path(__file__).parent.parent / "__init__.py")
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)


DEVICES = {"devices": [
    {"id": "light.lampara", "name": "Lámpara"},
    {"id": "light.leds_monitores", "name": "LEDs de los monitores"},
]}


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@mock.patch.dict(os.environ, {"BRIDGE_API_KEY": "k" * 32})
class PluginTest(unittest.TestCase):
    def call(self, params, reply=None):
        sent = []

        def urlopen(request, timeout):
            sent.append(request)
            return FakeResponse(json.dumps(reply or {"ok": True}).encode())

        with mock.patch.object(plugin.urllib.request, "urlopen", urlopen):
            result = json.loads(plugin.handle(params))
        return result, sent

    def test_list_discovers_devices(self):
        result, sent = self.call({"action": "list"}, reply={"devices": []})
        self.assertEqual(result, {"success": True, "action": "list", "result": {"devices": []}})
        self.assertEqual((sent[0].get_method(), sent[0].full_url), ("GET", f"{plugin.BRIDGE_URL}/devices"))
        self.assertEqual(sent[0].get_header("Authorization"), "Bearer " + "k" * 32)

    def test_status_reads_one_device(self):
        _, sent = self.call({"action": "status", "device": "light.leds_monitores"})
        self.assertEqual(sent[0].full_url, f"{plugin.BRIDGE_URL}/devices/light.leds_monitores")

    def test_power_actions_send_no_body_nor_content_type(self):
        _, sent = self.call({"action": "off", "device": "switch.ventilador", "brightness": 50})
        self.assertEqual((sent[0].get_method(), sent[0].full_url), ("POST", f"{plugin.BRIDGE_URL}/devices/switch.ventilador/off"))
        self.assertIsNone(sent[0].data)
        self.assertIsNone(sent[0].get_header("Content-type"))

    def test_actions_forward_only_their_fields(self):
        _, sent = self.call({"action": "color", "device": "light.leds_monitores", "rgb": [0, 255, 0], "position": 3})
        self.assertEqual(json.loads(sent[0].data), {"rgb": [0, 255, 0]})
        self.assertEqual(sent[0].get_header("Content-type"), "application/json")
        _, sent = self.call({"action": "temperature", "device": "climate.aire", "temperature": 22.5})
        self.assertEqual(json.loads(sent[0].data), {"temperature": 22.5})

    def test_rejects_bad_action_or_missing_device_without_calling_bridge(self):
        for params in (
            {"action": "explode", "device": "light.x"},
            {"action": "on"},
            {"action": "on", "device": "  "},
        ):
            result, sent = self.call(params)
            self.assertFalse(result["success"], params)
            self.assertEqual(sent, [], params)

    def test_unknown_or_malicious_names_never_reach_an_action_route(self):
        for device in ("../config", "light.x/../../devices", "cocina"):
            result, sent = self.call({"action": "on", "device": device}, reply=DEVICES)
            self.assertFalse(result["success"], device)
            self.assertIn("Lámpara", result["error"])
            self.assertEqual([r.get_method() for r in sent], ["GET"], device)

    def test_acts_directly_by_name_ignoring_case_and_accents(self):
        for device in ("lampara", "Mi LÁMPARA", "leds de los monitores"):
            result, sent = self.call({"action": "off", "device": device}, reply=DEVICES)
            self.assertTrue(result["success"], device)
            self.assertEqual(sent[-1].get_method(), "POST", device)
        self.assertEqual(sent[-1].full_url, f"{plugin.BRIDGE_URL}/devices/light.leds_monitores/off")
        _, sent = self.call({"action": "status", "device": "Lámpara"}, reply=DEVICES)
        self.assertEqual(sent[-1].full_url, f"{plugin.BRIDGE_URL}/devices/light.lampara")

    def test_ambiguous_name_lists_candidates(self):
        result, sent = self.call({"action": "on", "device": "luz"}, reply={"devices": [
            {"id": "light.luz_sala", "name": "Luz sala"}, {"id": "light.luz_cuarto", "name": "Luz cuarto"},
        ]})
        self.assertFalse(result["success"])
        self.assertIn("ambiguo", result["error"])
        self.assertEqual(len(sent), 1)

    def test_reports_bridge_error_detail(self):
        error = urllib.error.HTTPError("u", 400, "Bad Request", {}, io.BytesIO(b'{"error": "Action not supported by this device"}'))
        with mock.patch.object(plugin.urllib.request, "urlopen", side_effect=error):
            result = json.loads(plugin.handle({"action": "color", "device": "switch.x", "rgb": [1, 2, 3]}))
        self.assertEqual(result, {"success": False, "error": "Home Bridge devolvió HTTP 400: Action not supported by this device"})


HOME = {"devices": [
    {"id": "light.lampara", "name": "Lámpara", "domain": "light"},
    {"id": "light.leds_monitores", "name": "Mic Enable Leds Monitores", "domain": "light"},
    {"id": "switch.impresora", "name": "Impresora", "domain": "switch"},
]}


@mock.patch.dict(os.environ, {"BRIDGE_API_KEY": "k" * 32})
class FastPathTest(unittest.TestCase):
    def hook(self, message):
        sent = []

        def urlopen(request, timeout):
            sent.append(request)
            return FakeResponse(json.dumps(HOME if request.get_method() == "GET" else {"confirmed": True}).encode())

        with mock.patch.object(plugin.urllib.request, "urlopen", urlopen):
            result = plugin.fast_path_hook(user_message=message, platform="telegram")
        return result, [r.full_url for r in sent if r.get_method() == "POST"]

    def test_all_lights_skip_switches(self):
        result, posts = self.hook('"Apaga todas las luces."')
        self.assertEqual(posts, [f"{plugin.BRIDGE_URL}/devices/light.lampara/off",
                                 f"{plugin.BRIDGE_URL}/devices/light.leds_monitores/off"])
        self.assertIn("YA se ejecutó", result["context"])

    def test_single_device_by_name(self):
        _, posts = self.hook('"Apara las luces."')  # Whisper mishearing of "Apaga"
        self.assertEqual(len(posts), 2)
        for message in ('"Prende la lámpara, por favor."', "enciende los leds", '"Finnip, apaga la impresora"'):
            _, posts = self.hook(message)
            self.assertEqual(len(posts), 1, message)
        self.assertEqual(posts, [f"{plugin.BRIDGE_URL}/devices/switch.impresora/off"])

    def test_leaves_anything_else_to_the_model(self):
        for message in ('"Apaga la lámpara en diez minutos"', '"apaga la lámpara y la impresora"',
                        '"apaga la luz"', '"no apagues las luces"', '"¿apagaste las luces?"',
                        '"pon la lámpara al 30"', "apaga la lámpara\nluego dime la hora", None):
            result, posts = self.hook(message)
            self.assertIsNone(result, message)
            self.assertEqual(posts, [], message)

    def test_bridge_failure_hands_back_to_model(self):
        with mock.patch.object(plugin.urllib.request, "urlopen", side_effect=urllib.error.URLError("x")):
            result = plugin.fast_path_hook(user_message='"apaga las luces"')
        self.assertIn("falló", result["context"])


if __name__ == "__main__":
    unittest.main()
