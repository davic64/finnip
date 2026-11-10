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

    def test_color_order(self):
        sent = []

        def urlopen(request, timeout):
            sent.append(request)
            return FakeResponse(json.dumps(HOME if request.get_method() == "GET" else {"confirmed": True}).encode())

        with mock.patch.object(plugin.urllib.request, "urlopen", urlopen):
            result = plugin.fast_path_hook(user_message="Pon los monitores en rojo.")
        post = [r for r in sent if r.get_method() == "POST"]
        self.assertEqual([r.full_url for r in post], [f"{plugin.BRIDGE_URL}/devices/light.leds_monitores/color"])
        self.assertEqual(json.loads(post[0].data), {"rgb": [255, 0, 0]})
        self.assertIn("YA se ejecutó", result["context"])
        for message in ("cambia los monitores a azul", "ponme la lámpara de color verde"):
            self.assertEqual(self.hook(message)[1][0].rsplit("/", 1)[1], "color", message)
        for message in ("pon música", "pon los monitores en rojo en 5 minutos", "¿pongo los monitores en rojo?"):
            self.assertEqual(self.hook(message), (None, []), message)

    def test_bridge_failure_hands_back_to_model(self):
        with mock.patch.object(plugin.urllib.request, "urlopen", side_effect=urllib.error.URLError("x")):
            result = plugin.fast_path_hook(user_message='"apaga las luces"')
        self.assertIn("falló", result["context"])



    def test_alexa_actions_forward_their_fields(self):
        cases = [({"action": "play", "device": "echo", "query": "Coldplay"}, "play", {"query": "Coldplay"}),
                 ({"action": "command", "device": "echo", "text": "pon una alarma a las 7"}, "command",
                  {"text": "pon una alarma a las 7"}),
                 ({"action": "volume", "device": "echo", "volume": 40}, "volume", {"volume": 40})]
        for params, action, body in cases:
            sent = []
            def bridge(method, path, body=None):
                sent.append((method, path, body))
                return {"devices": [{"id": "media_player.echo", "name": "Echo Dave"}]} if method == "GET" else {}
            with mock.patch.object(plugin, "call_bridge", bridge):
                json.loads(plugin.handle(params))
            self.assertEqual(sent[-1], ("POST", f"/devices/media_player.echo/{action}", body))

    def test_music_orders(self):
        cases = {
            '"Pausa la música."': ("pause", None),
            "Finnip, pausa": ("pause", None),
            "para la música": ("pause", None),
            "Reanuda la música": ("resume", None),
            "sigue la música": ("resume", None),
            "Finnip, reproduce algo de Queen": ("play", {"query": "algo de Queen"}),
            "reproduce música de los 80": ("play", {"query": "música de los 80"}),
            "Reproduce Iron Man. De Black Sabbath.": ("play", {"query": "Iron Man De Black Sabbath"}),
            "volumen al 20 por ciento": ("volume", {"volume": 20}),
            "Reproduce Bohemian Rhapsody de Queen en Alexa": ("play", {"query": "Bohemian Rhapsody de Queen"}),
            "pon el volumen al 30": ("volume", {"volume": 30}),
            "volumen 45 %": ("volume", {"volume": 45}),
        }
        for message, expected in cases.items():
            self.assertEqual(plugin.parse_music_order(message), expected, message)
        for message in ("para mañana tengo junta", "¿qué está sonando?", "sigue explicándome lo de ayer por favor",
                        "volumen 300", "reproduce", "continúa con la explicación",
                        "Reproduce la música que tú quieras", "reproduce algo", "Reprodúceme lo que sea", "reproduce algo bueno",
                        "Reproduce la música que quieras para hacer el aseo en mi cuarto", "reproduce música para concentrarme",
                        "reproduce algo tranquilo para programar", "Reproduce canciones para trabajar"):
            self.assertIsNone(plugin.parse_music_order(message), message)

    def test_music_fast_path_runs_on_the_only_speaker(self):
        sent = []
        def bridge(method, path, body=None):
            sent.append((method, path, body))
            if method == "GET":
                return {"devices": [{"id": "light.lampara", "domain": "light"},
                                    {"id": "media_player.echo", "domain": "media_player"}]}
            return {"confirmed": True}
        with mock.patch.object(plugin, "call_bridge", bridge):
            out = plugin.fast_path_hook(user_message="Pausa la música")
        self.assertEqual(sent[-1], ("POST", "/devices/media_player.echo/pause", None))
        self.assertIn("YA se ejecutó", out["context"])

    def test_bare_continua_resumes_only_paused_music(self):
        for state, resumed in (("paused", True), ("idle", False), ("playing", False)):
            sent = []
            def bridge(method, path, body=None):
                sent.append((method, path))
                return {"devices": [{"id": "media_player.echo", "domain": "media_player", "state": state}]} \
                    if method == "GET" else {"confirmed": True}
            with mock.patch.object(plugin, "call_bridge", bridge):
                out = plugin.fast_path_hook(user_message="Continúa.")
            self.assertEqual(("POST", "/devices/media_player.echo/resume") in sent, resumed, state)
            self.assertEqual(out is not None, resumed, state)
class ModeTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(plugin.parse_mode_order("Modo estudio."), "modo estudio")
        self.assertEqual(plugin.parse_mode_order("Finnip, activa el modo trabajo profundo"), "modo trabajo profundo")
        self.assertEqual(plugin.parse_mode_order("pon modo cálido por favor"), "modo calido")
        self.assertEqual(plugin.parse_mode_order("Voy a ver una película"), "modo cine")
        self.assertEqual(plugin.parse_mode_order("Modio Trabajo Profundo."), "modo trabajo profundo")
        self.assertIsNone(plugin.parse_mode_order("¿qué modo tienes?"))
        self.assertIsNone(plugin.parse_mode_order("explícame el modo subjuntivo en inglés por favor ahora"))

    def test_runs_the_script_and_lets_the_model_pick_music(self):
        calls = []
        def bridge(method, path, body=None):
            calls.append((method, path))
            if path == "/devices":
                return {"devices": [{"id": "script.modo_calido", "name": "Modo cálido", "domain": "script"},
                                    {"id": "script.modo_cine", "name": "Modo cine", "domain": "script", "music": False},
                                    {"id": "light.lampara", "name": "Lámpara", "domain": "light"}]}
            return {"confirmed": True}
        with mock.patch.object(plugin, "call_bridge", bridge):
            warm = plugin.fast_path_hook(user_message="Activa el modo cálido")
            movie = plugin.fast_path_hook(user_message="vamos a ver una peli")
            unknown = plugin.fast_path_hook(user_message="modo fiesta")
        self.assertIn(("POST", "/devices/script.modo_calido/run"), calls)
        self.assertIn(("POST", "/devices/script.modo_cine/run"), calls)
        self.assertIn("reprodúcelo", warm["context"])
        self.assertIn("no lleva música", movie["context"])
        self.assertIn("no existe", unknown["context"])
        self.assertIn("Modo cálido, Modo cine", unknown["context"])
        self.assertNotIn(("POST", "/devices/script.modo_fiesta/run"), calls)



@mock.patch.dict(os.environ, {"BRIDGE_API_KEY": "k" * 32})
class AdminTest(unittest.TestCase):
    def call(self, params, replies=None):
        sent = []
        def bridge(method, path, body=None):
            sent.append((method, path, body))
            return (replies or {}).get(path, {"ok": True})
        with mock.patch.object(plugin, "call_bridge", bridge):
            return json.loads(plugin.handle(params)), sent

    def test_slugify(self):
        self.assertEqual(plugin.slugify("Modo Lectura Nocturna"), "lectura_nocturna")
        self.assertEqual(plugin.slugify("cálido / año"), "calido_ano")
        self.assertRaises(ValueError, plugin.slugify, "modo")

    def test_expose_finds_the_name_among_candidates(self):
        candidates = {"/candidates": {"candidates": [{"id": "light.lampara_buro", "name": "Lámpara del buró"}]}}
        _, sent = self.call({"action": "expose", "device": "lámpara del buró"}, candidates)
        self.assertEqual(sent, [("GET", "/candidates", None), ("POST", "/devices/light.lampara_buro/expose", None)])

    def test_mode_routes_use_the_slug(self):
        _, read = self.call({"action": "mode", "name": "Modo estudio"})
        _, deleted = self.call({"action": "delete_mode", "name": "Cine"})
        _, listed = self.call({"action": "modes"})
        self.assertEqual((read, deleted, listed), ([("GET", "/modes/estudio", None)], [("DELETE", "/modes/cine", None)],
                                                   [("GET", "/modes", None)]))

    def test_save_mode_resolves_step_devices(self):
        _, sent = self.call({"action": "save_mode", "name": "lectura", "music": False, "steps": [
            {"device": "lámpara", "action": "color_temp", "params": {"kelvin": 2700}},
            {"device": "light.leds_monitores", "action": "off"},
        ]}, {"/devices": DEVICES})
        self.assertEqual(sent[-1], ("PUT", "/modes/lectura", {"name": "lectura", "music": False, "steps": [
            {"device": "light.lampara", "action": "color_temp", "params": {"kelvin": 2700}},
            {"device": "light.leds_monitores", "action": "off", "params": {}},
        ]}))

    def test_save_mode_without_steps_never_calls_the_bridge(self):
        result, sent = self.call({"action": "save_mode", "name": "vacío"})
        self.assertFalse(result["success"])
        self.assertEqual(sent, [])


if __name__ == "__main__":
    unittest.main()
