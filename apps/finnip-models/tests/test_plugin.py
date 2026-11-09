import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

# The plugin directory name has a hyphen, so load __init__.py by path.
spec = importlib.util.spec_from_file_location("finnip_models", Path(__file__).parent.parent / "__init__.py")
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)

MODELS = [{"id": "deepseek/deepseek-v4", "created": 1}, {"id": "deepseek/deepseek-v4.1", "created": 3},
          {"id": "deepseek/deepseek-v4.1-flash-1017", "created": 5}, {"id": "deepseek/deepseek-v4.1:batch", "created": 6},
          {"id": "deepseek/deepseek-v4.1-flash", "created": 4},
          {"id": "z-ai/glm-5.3-prime", "created": 2}, {"id": "z-ai/glm-5.3-flashx-legal", "created": 7}]


class OrderTest(unittest.TestCase):
    def test_orders(self):
        self.assertEqual(plugin.model_order("Usa Opus."), ("use", "opus"))
        self.assertEqual(plugin.model_order("Oye Finnip, usa sonnet"), ("use", "sonnet"))
        self.assertEqual(plugin.model_order("Regresa al modelo normal"), ("use", "normal"))
        self.assertEqual(plugin.model_order('"cambia a Opus"'), ("use", "opus"))  # a Telegram voice note
        self.assertEqual(plugin.model_order("Que el normal sea GLM 5.3"), ("set_normal", "glm 5 3"))
        self.assertEqual(plugin.model_order("cambia el modelo normal a DeepSeek"), ("set_normal", "deepseek"))
        self.assertIsNone(plugin.model_order("usa la lámpara"))
        self.assertEqual(plugin.model_order("¿Qué modelo usas?"), ("which", None))
        self.assertEqual(plugin.model_order("Finnip, con qué modelo estás"), ("which", None))
        self.assertIsNone(plugin.model_order("qué modelo de auto me recomiendas"))

    def test_pick_model(self):
        self.assertEqual(plugin.pick_model("deepseek", MODELS), "deepseek/deepseek-v4.1")
        self.assertEqual(plugin.pick_model("deepseek flash 4 1", MODELS), "deepseek/deepseek-v4.1-flash")  # undated first
        self.assertEqual(plugin.pick_model("glm 5 3", MODELS), "z-ai/glm-5.3-prime")
        self.assertIsNone(plugin.pick_model("llama", MODELS))
        self.assertEqual(plugin.model_label("z-ai/glm-5.3-prime"), "GLM 5.3 prime")
        self.assertEqual(plugin.model_label("~deepseek/deepseek-pro-latest"), "Deepseek pro latest")


class StateTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "model.json")

    def tearDown(self):
        self.dir.cleanup()

    def test_orders_change_the_shared_route(self):
        self.assertEqual(plugin.route(plugin.load_state(self.path)), ("anthropic", "claude-sonnet-5-5"))
        msg, chosen = plugin.apply_order(("use", "normal"), self.path)
        self.assertIsNone(chosen)
        self.assertIn("Aún no tengo", msg)
        msg, chosen = plugin.apply_order(("set_normal", "deepseek flash"), self.path, models=lambda: MODELS)
        self.assertEqual(chosen, ("openrouter", "deepseek/deepseek-v4.1-flash"))
        self.assertEqual(plugin.apply_order(("use", "opus"), self.path)[1], ("anthropic", "claude-opus-5-5"))
        self.assertEqual(plugin.apply_order(("use", "normal"), self.path)[1], ("openrouter", "deepseek/deepseek-v4.1-flash"))
        with open(self.path) as f:
            self.assertEqual(json.load(f), {"use": "normal", "normal": "deepseek/deepseek-v4.1-flash"})
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o660)
        self.assertEqual(plugin.apply_order(("which", None), self.path), ("Ahora uso Deepseek v4.1 flash por OpenRouter, señor.", None))

    def test_telegram_hook_rewrites_only_the_owners_orders(self):
        def event(text, user="42", platform="telegram"):
            return SimpleNamespace(text=text, source=SimpleNamespace(user_id=user, platform=SimpleNamespace(value=platform)))
        with mock.patch.dict(os.environ, {"TELEGRAM_ALLOWED_USERS": "42"}), \
                mock.patch.object(plugin, "STATE_PATH", self.path), \
                mock.patch.object(plugin, "openrouter_models", lambda: MODELS):
            self.assertEqual(plugin.telegram_hook(event=event("usa Opus")),
                             {"action": "rewrite", "text": "/model claude-opus-5-5 --provider anthropic --global"})
            self.assertIsNone(plugin.telegram_hook(event=event("usa Opus", user="666")))  # not the owner
            self.assertIsNone(plugin.telegram_hook(event=event("usa Opus", platform="discord")))
            self.assertIsNone(plugin.telegram_hook(event=event("enciende la lámpara")))
            self.assertIsNone(plugin.telegram_hook(event=event("/model x")))
        self.assertEqual(plugin.load_state(self.path)["use"], "opus")  # the stranger changed nothing


if __name__ == "__main__":
    unittest.main()
