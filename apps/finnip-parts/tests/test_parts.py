import json
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from parts import cura, scad, server, store

HAS_OPENSCAD = shutil.which(scad.OPENSCAD) is not None
HAS_CURA = cura.ENGINE.exists() and cura.RESOURCES.exists()
BRACKET = """
difference() {
    cube([40, 20, 5]);
    for (x = [10, 30]) translate([x, 10, -1]) cylinder(d = 4, h = 7, $fn = 32);
}
"""


class CheckTest(unittest.TestCase):
    def test_rejects_file_access(self):
        for code in ('import("/etc/passwd");', "include <x.scad>", "use <MCAD/gears.scad>",
                     'surface(file = "/data/x.dat");', 'dxf_linear_extrude(file="a.dxf");'):
            with self.assertRaises(scad.RenderError, msg=code):
                scad.check(code)

    def test_allows_the_words_in_comments_strings_and_names(self):
        scad.check('// import the lid later\n/* use M3 */ surface_finish = 1; text("include");\ncube(surface_finish);')


@unittest.skipUnless(HAS_OPENSCAD, "openscad not installed")
class RenderTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)

    def test_bracket_is_centered_on_the_bed(self):
        result = scad.render(BRACKET, self.dir / "v1.scad", self.dir / "v1.stl")
        self.assertEqual(result, {"size_mm": [40.0, 20.0, 5.0], "warnings": []})
        low, high = scad.bounds(scad.read_stl(self.dir / "v1.stl"))
        self.assertEqual([round(v, 2) for v in low + high], [-20, -10, 0, 20, 10, 5])

    def test_too_big_for_the_bed(self):
        result = scad.render("cube([300, 10, 10]);", self.dir / "v1.scad", self.dir / "v1.stl")
        self.assertIn("No cabe", result["warnings"][0])

    def test_openscad_error_is_returned(self):
        with self.assertRaisesRegex(scad.RenderError, "OpenSCAD|vacía"):
            scad.render("cube([10, 10, 10]", self.dir / "v1.scad", self.dir / "v1.stl")

    def test_slow_render_is_stopped(self):
        slow = "minkowski() { for (i = [0:400]) translate([i, 0, 0]) sphere(5, $fn = 60); sphere(2, $fn = 60); }"
        with mock.patch.object(scad, "TIMEOUT_S", 1), self.assertRaisesRegex(scad.RenderError, "tardó"):
            scad.render(slow, self.dir / "v1.scad", self.dir / "v1.stl")


@unittest.skipUnless(HAS_CURA, "Cura resources not installed")
class CuraStackTest(unittest.TestCase):
    def test_material_profiles(self):
        pla, petg = cura.Machine("PLA"), cura.Machine("petg")
        self.assertEqual((pla.extruder.value("material_print_temperature"), pla.globals.value("material_bed_temperature")),
                         (200, 60))
        self.assertEqual((petg.extruder.value("material_print_temperature"), petg.globals.value("material_bed_temperature")),
                         (215, 70))
        self.assertEqual(petg.extruder.value("speed_layer_0"), 15)  # from base_0.4_PETG_standard
        self.assertEqual(pla.globals.value("layer_height"), 0.2)    # from base_global_standard

    def test_formulas_follow_per_part_settings(self):
        base = cura.Machine("PLA")
        machine = cura.Machine("PLA", {"infill_sparse_density": 40, "wall_line_count": 3})
        self.assertEqual(base.extruder.value("infill_sparse_density"), 20)
        # infill_line_distance is a formula of the density: twice as dense, half the distance
        self.assertAlmostEqual(machine.extruder.value("infill_line_distance") * 2, base.extruder.value("infill_line_distance"))
        self.assertEqual(machine.extruder_settings()["wall_line_count"], 3)

    def test_rejects_unknown_machine_and_out_of_range_settings(self):
        for bad, message in (({"nope": 1}, "no permitido"), ({"machine_start_gcode": "M104 S300"}, "no permitido"),
                             ({"layer_height": "abc"}, "inválido"), ({"infill_sparse_density": -5}, "fuera de rango"),
                             ({"adhesion_type": "glue"}, "acepta")):
            with self.assertRaisesRegex(cura.SettingsError, message, msg=bad):
                cura.Machine("PLA", bad)
        with self.assertRaisesRegex(cura.SettingsError, "Material"):
            cura.Machine("ABS")


@unittest.skipUnless(HAS_OPENSCAD and HAS_CURA, "openscad or CuraEngine not installed")
class StoreTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.store = store.Store(self.dir)

    def test_versions_are_kept_and_a_failed_render_changes_nothing(self):
        self.store.add_version("soporte", BRACKET, name="Soporte")
        self.store.add_version("soporte", BRACKET.replace("5]", "10]"), note="más alto")
        with self.assertRaises(scad.RenderError):
            self.store.add_version("soporte", 'import("x.stl");')
        part = self.store.get("soporte")
        self.assertEqual([v["size_mm"][2] for v in part["versions"]], [5.0, 10.0])
        self.assertIn("10]", part["current"]["code"])
        self.assertEqual(self.store.get("soporte", 1)["current"]["version"], 1)
        self.assertEqual(self.store.list()[0]["versions"], 2)

    def test_slice_in_pla_and_petg(self):
        self.store.add_version("soporte", BRACKET)
        pla = self.store.slice("soporte", 1)
        gcode = self.store.file("soporte", 1, "gcode")[0].read_text()
        self.assertIn("M109 S200", gcode)
        petg = self.store.slice("soporte", 1, "PETG", {"infill_sparse_density": 60})
        gcode = self.store.file("soporte", 1, "gcode")[0].read_text()
        self.assertIn("M109 S215", gcode)
        self.assertEqual((pla["material"], petg["material"], petg["settings"]), ("PLA", "PETG", {"infill_sparse_density": 60.0}))
        self.assertGreater(petg["grams"], pla["grams"])
        self.assertGreater(pla["seconds"], 0)
        self.assertEqual(self.store.get("soporte")["current"]["slice"]["material"], "PETG")


class ServerTest(unittest.TestCase):
    key = "k" * 32

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(store.Store(self.dir), self.key))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        self.base = f"http://127.0.0.1:{httpd.server_address[1]}"

    def call(self, method, path, body=None, key=key):
        request = urllib.request.Request(self.base + path, method=method,
                                         data=None if body is None else json.dumps(body).encode(),
                                         headers={"Authorization": f"Bearer {key}"} if key else {})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def test_auth_and_errors(self):
        self.assertEqual(self.call("GET", "/health", key=None)[0], 200)
        self.assertEqual(self.call("GET", "/parts", key="x" * 32)[0], 401)
        self.assertEqual(self.call("GET", "/parts"), (200, {"parts": []}))
        self.assertEqual(self.call("GET", "/parts/nada")[0], 404)
        status, body = self.call("POST", "/parts/malo/versions", {"code": 'import("/etc/passwd");'})
        self.assertEqual((status, "import" in body["error"]), (400, True))
        self.assertEqual(self.call("POST", "/parts/..%2Fetc/versions", {"code": "cube(1);"})[0], 400)
        self.assertEqual(self.call("GET", "/parts/malo")[0], 404)  # the rejected code created nothing


if __name__ == "__main__":
    unittest.main()
