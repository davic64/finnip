import importlib.util
import json
import unittest
from pathlib import Path
from unittest import mock

spec = importlib.util.spec_from_file_location("finnip_projects", Path(__file__).parent.parent / "__init__.py")
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)


class PluginTest(unittest.TestCase):
    def call(self, params):
        sent = []
        with mock.patch.object(plugin, "call_gateway", lambda body: sent.append(body) or {"ok": True}):
            return json.loads(plugin.handle(params)), sent

    def test_names_become_folders(self):
        self.assertEqual(plugin.slugify("Mi Tienda Ñandú"), "mi-tienda-nandu")
        self.assertRaises(ValueError, plugin.slugify, "  ")

    def test_only_known_fields_reach_the_mac(self):
        result, sent = self.call({"action": "task", "name": "Tienda", "request": "agrega un login", "where": "cloud"})
        self.assertTrue(result["success"])
        self.assertEqual(sent, [{"action": "task", "where": "cloud", "name": "tienda", "request": "agrega un login",
                                 "confirmed": False}])
        _, sent = self.call({"action": "create", "name": "finnip", "repo": "davic64/finnip"})
        self.assertEqual(sent[0]["repo"], "davic64/finnip")

    def test_documents_folders_find_and_delete(self):
        _, sent = self.call({"action": "run", "path": "Documents/clientes/Tienda Vieja"})
        self.assertEqual(sent, [{"action": "run", "where": "local", "path": "Documents/clientes/Tienda Vieja"}])
        _, sent = self.call({"action": "find", "name": "Tienda Vieja"})
        self.assertEqual(sent[0]["name"], "Tienda Vieja")
        _, sent = self.call({"action": "delete", "name": "tienda", "where": "cloud", "confirmed": True})
        self.assertEqual(sent, [{"action": "delete", "where": "cloud", "name": "tienda", "confirmed": True}])

    def test_refusals(self):
        for params in ({"action": "exec"}, {"action": "task", "name": "x"}):
            result, sent = self.call(params)
            self.assertFalse(result["success"])
            self.assertEqual(sent, [])


if __name__ == "__main__":
    unittest.main()
