import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# The plugin directory name has a hyphen, so load __init__.py by path.
spec = importlib.util.spec_from_file_location("finnip_printer", Path(__file__).parent.parent / "__init__.py")
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)


class FakePrinter:
    """OctoPrint as the plugin sees it: temperatures, a job state, and the commands it received."""
    def __init__(self, nozzle=25, bed=25, job="Operational", connected=True, printing=False):
        self.nozzle, self.bed, self.job, self.connected, self.printing = nozzle, bed, job, connected, printing
        self.sent, self.connection, self.power = [], [], []

    def read(self):
        printer = None
        if self.connected:
            printer = {"state": {"text": "Operational", "flags": {"printing": self.printing}},
                       "temperature": {"tool0": {"actual": self.nozzle, "target": 0},
                                       "bed": {"actual": self.bed, "target": 0}}}
        return printer, {"state": self.job, "job": {"file": {"display": "gato.gcode"}},
                         "progress": {"completion": 42.0, "printTimeLeft": 4500}}

    def octoprint(self, method, path, body=None):
        if path == "/api/connection":
            self.connection.append(body["command"])
        return {}

    def patches(self):
        return [mock.patch.object(plugin, "read", self.read),
                mock.patch.object(plugin, "gcode", self.sent.extend),
                mock.patch.object(plugin, "octoprint", self.octoprint),
                mock.patch.object(plugin, "bridge_power", self.power.append)]


class PrinterTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "state.json")
        self.fake = FakePrinter()
        for patch in self.fake.patches() + [mock.patch.object(plugin, "STATE_PATH", self.path)]:
            patch.start()
            self.addCleanup(patch.stop)
        plugin._last["job"] = None

    def tearDown(self):
        self.dir.cleanup()

    def test_load_waits_for_the_nozzle_then_purges(self):
        self.assertIn("200 °C", plugin.run({"action": "load"}, now=0))
        self.assertEqual(self.fake.sent, ["M104 S200"])
        self.assertEqual(plugin.step(now=5), [])          # still cold: nothing to say
        self.fake.nozzle = 198
        said = plugin.step(now=60)
        self.assertIn("es momento de meter el filamento", said[0])
        self.assertEqual(plugin.load_state()["intent"]["do"], "keep_hot")
        plugin.run({"action": "purge"}, now=70)
        self.assertEqual(self.fake.sent[-2:], plugin.PURGE)

    def test_unload_retracts_when_hot_and_keeps_it_hot_for_cleaning(self):
        plugin.run({"action": "unload", "material": "petg"}, now=0)
        self.assertEqual(self.fake.sent, ["M104 S230"])
        self.fake.nozzle = 229
        self.assertIn("es momento de sacarlo", plugin.step(now=30)[0])
        self.assertEqual(self.fake.sent[-3:], plugin.UNLOAD)
        self.assertIn("toca limpiar", plugin.run({"action": "removed"}, now=40))
        self.assertEqual(plugin.step(now=41), [])         # stays hot while cleaning
        self.assertIn("la apagué", plugin.step(now=40 + plugin.KEEP_HOT + 1)[0])
        self.assertEqual(self.fake.sent[-3:], plugin.COOL)

    def test_power_off_only_once_the_nozzle_is_cool(self):
        self.fake.nozzle = 180
        plugin.run({"action": "power_off"}, now=0)
        self.assertEqual(plugin.step(now=10), [])
        self.assertEqual(self.fake.power, [])
        self.fake.nozzle = 45
        self.assertIn("la apagué", plugin.step(now=300)[0])
        self.assertEqual(self.fake.power, [False])
        self.assertEqual(self.fake.connection, ["disconnect"])

    def test_finished_print_cools_and_then_powers_off(self):
        self.fake.job, self.fake.nozzle = "Printing", 200
        self.assertEqual(plugin.step(now=0), [])
        self.fake.job = "Operational"
        self.assertIn("Terminó la impresión de gato.gcode", plugin.step(now=10)[0])
        self.assertEqual(self.fake.sent, plugin.COOL)
        self.fake.nozzle = 40
        self.assertIn("la apagué", plugin.step(now=400)[0])
        self.assertEqual(self.fake.power, [False])

    def test_refuses_heat_or_power_while_printing_but_reports_progress(self):
        self.fake.printing = True
        with self.assertRaises(RuntimeError):
            plugin.run({"action": "power_off"})
        self.assertEqual(self.fake.sent, [])
        self.assertIn("le faltan unos 1 h 15 min", plugin.status(*self.fake.read()))

    def test_power_on_connects_when_the_printer_answers(self):
        self.fake.connected = False
        plugin.run({"action": "power_on"}, now=0)
        self.assertEqual(self.fake.power, [True])
        self.assertEqual(plugin.step(now=11), [])
        self.assertEqual(self.fake.connection, ["connect"])
        self.fake.connected = True
        self.assertIn("conectada", plugin.step(now=20)[0])

    def test_heater_that_never_heats_gives_up(self):
        plugin.run({"action": "preheat"}, now=0)
        self.assertIn("no llegó a la temperatura", plugin.step(now=plugin.HEAT_TIMEOUT + 1)[0])
        self.assertEqual(self.fake.sent[-3:], plugin.COOL)


if __name__ == "__main__":
    unittest.main()
