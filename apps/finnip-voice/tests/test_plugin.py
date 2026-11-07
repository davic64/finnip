import importlib.util
import io
import json
import os
import sys
import tempfile
import types
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

# Hermes is not installed in CI: stub the base class the plugin subclasses.
stub = types.ModuleType("agent.tts_provider")
stub.TTSProvider = type("TTSProvider", (), {})
sys.modules.setdefault("agent", types.ModuleType("agent"))
sys.modules["agent.tts_provider"] = stub

# The plugin directory name has a hyphen, so load __init__.py by path.
spec = importlib.util.spec_from_file_location("finnip_voice", Path(__file__).parent.parent / "__init__.py")
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)

KEY = "fish-secret-key-123"


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@mock.patch.dict(os.environ, {"FISH_API_KEY": KEY})
class FishProviderTest(unittest.TestCase):
    def setUp(self):
        self.provider = plugin.FishTTSProvider()
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def synthesize(self, output_name="reply.ogg", audio=b"OggS-audio", **kwargs):
        sent = []

        def urlopen(request, timeout):
            sent.append(request)
            return FakeResponse(audio)

        with mock.patch.object(plugin.urllib.request, "urlopen", urlopen):
            path = self.provider.synthesize("Listo, señor.", os.path.join(self.dir.name, output_name), **kwargs)
        return path, sent

    def test_requests_opus_with_default_voice_and_model(self):
        path, sent = self.synthesize()
        request = sent[0]
        self.assertEqual((request.get_method(), request.full_url), ("POST", plugin.FISH_TTS_URL))
        self.assertEqual(request.get_header("Authorization"), f"Bearer {KEY}")
        self.assertEqual(request.get_header("Model"), "s2.1-pro-free")
        self.assertEqual(json.loads(request.data), {
            "text": "Listo, señor.", "reference_id": "ae74d1059517440aa6e5d2d50598d179", "format": "opus"})
        self.assertTrue(path.endswith(".ogg"))
        self.assertEqual(Path(path).read_bytes(), b"OggS-audio")

    def test_opus_format_forces_ogg_extension(self):
        path, sent = self.synthesize(output_name="reply.mp3", format="opus")
        self.assertEqual(json.loads(sent[0].data)["format"], "opus")
        self.assertTrue(path.endswith(".ogg"))

    def test_other_formats_use_mp3(self):
        path, sent = self.synthesize(output_name="reply.mp3", format="mp3")
        self.assertEqual(json.loads(sent[0].data)["format"], "mp3")
        self.assertTrue(path.endswith(".mp3"))

    def test_configured_voice_and_model_override_defaults(self):
        _, sent = self.synthesize(voice="b" * 32, model="s2.1-pro")
        self.assertEqual(json.loads(sent[0].data)["reference_id"], "b" * 32)
        self.assertEqual(sent[0].get_header("Model"), "s2.1-pro")

    def test_never_sends_language(self):
        _, sent = self.synthesize()
        self.assertNotIn("language", json.loads(sent[0].data))

    def test_missing_key_fails_without_calling_fish(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "FISH_API_KEY"):
                self.synthesize()
            self.assertFalse(self.provider.is_available())

    def test_http_error_reports_code_but_never_the_key(self):
        error = urllib.error.HTTPError(plugin.FISH_TTS_URL, 402, "Payment Required", {}, io.BytesIO(b"insufficient credit"))
        with mock.patch.object(plugin.urllib.request, "urlopen", side_effect=error):
            with self.assertRaises(RuntimeError) as raised:
                self.provider.synthesize("hola", os.path.join(self.dir.name, "r.ogg"))
        message = str(raised.exception)
        self.assertEqual(message, "Fish Audio devolvió HTTP 402: insufficient credit")
        self.assertNotIn(KEY, message)
        self.assertIsNone(raised.exception.__cause__)

    def test_network_error_is_reported_without_the_key(self):
        with mock.patch.object(plugin.urllib.request, "urlopen", side_effect=urllib.error.URLError("timed out")):
            with self.assertRaisesRegex(RuntimeError, "No se pudo conectar con Fish Audio") as raised:
                self.provider.synthesize("hola", os.path.join(self.dir.name, "r.ogg"))
        self.assertNotIn(KEY, str(raised.exception))

    def test_empty_audio_is_an_error_and_writes_nothing(self):
        with self.assertRaisesRegex(RuntimeError, "vacío"):
            self.synthesize(audio=b"")
        self.assertEqual(os.listdir(self.dir.name), [])

    def test_registers_a_voice_compatible_fish_provider(self):
        ctx = mock.Mock()
        plugin.register(ctx)
        provider = ctx.register_tts_provider.call_args.args[0]
        self.assertEqual(provider.name, "fish")
        self.assertTrue(provider.voice_compatible)


if __name__ == "__main__":
    unittest.main()
