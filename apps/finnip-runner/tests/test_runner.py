import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("runner", Path(__file__).parent.parent / "runner.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class RunnerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.done = []
        self.routes = []
        self.projects = runner.Projects(self.tmp.name, notify=self.done.append,
                                        caddy=lambda name, port: self.routes.append((name, port)))

    def test_names_and_repos_are_checked(self):
        for bad in ("../x", "X", "", "-a", "a b", None):
            self.assertRaises(runner.Refused, self.projects.handle, {"action": "create", "name": bad})
        self.assertEqual(runner.valid_repo("https://github.com/davic64/finnip.git"), "davic64/finnip")
        self.assertIsNone(runner.valid_repo("a/b; rm -rf ~"))
        self.assertIsNone(runner.valid_repo("../../etc"))
        self.assertRaises(runner.Refused, self.projects.handle, {"action": "exec"})

    def test_create_and_list(self):
        self.assertEqual(self.projects.handle({"action": "create", "name": "tienda"})["created"], "tienda")
        self.assertTrue((Path(self.tmp.name) / "tienda" / ".git").exists())
        self.assertRaises(runner.Refused, self.projects.handle, {"action": "create", "name": "tienda"})
        listed = self.projects.handle({"action": "list"})["projects"]
        self.assertEqual([(p["name"], p["git"]) for p in listed], [("tienda", True)])

    def test_task_reports_what_needs_a_yes(self):
        (Path(self.tmp.name) / "tienda").mkdir()

        class Out:
            returncode = 0
            stderr = ""
            stdout = json.dumps({"result": "Hice el login.\nCONFIRMAR: subirlo con git push", "session_id": "s1",
                                 "permission_denials": [{"tool_name": "Bash", "tool_input": {"command": "git push"}}]})

        asked = []
        self.projects._claude = lambda path, request, confirmed, session: asked.append((request, confirmed, session)) or Out()
        self.projects.handle({"action": "task", "name": "tienda", "request": "agrega login"})
        for _ in range(100):
            if self.done:
                break
            import time
            time.sleep(0.02)
        self.assertEqual(self.done[0]["pending"], ["subirlo con git push", "correr git push"])
        self.projects.handle({"action": "task", "name": "tienda", "request": "Confirmado: súbelo", "confirmed": True})
        for _ in range(100):
            if len(self.done) == 2:
                break
            import time
            time.sleep(0.02)
        self.assertEqual(asked, [("agrega login", False, None), ("Confirmado: súbelo", True, "s1")])

    def test_delete_needs_a_yes_and_goes_to_the_trash(self):
        self.projects.handle({"action": "create", "name": "tienda"})
        self.assertRaises(runner.Refused, self.projects.handle, {"action": "delete", "name": "tienda"})
        self.projects.handle({"action": "delete", "name": "tienda", "confirmed": True})
        root = Path(self.tmp.name)
        self.assertFalse((root / "tienda").exists())
        self.assertTrue((root / ".trash" / "tienda" / ".git").exists())
        self.assertEqual(self.projects.handle({"action": "list"})["projects"], [])  # .trash stays hidden

    def test_dev_command_uses_the_preview_port(self):
        path = Path(self.tmp.name)
        (path / "package.json").write_text(json.dumps({"scripts": {"dev": "vite"}}))
        (path / "pnpm-lock.yaml").write_text("")
        self.assertEqual(runner.Projects.dev_command(path, 4101), ("pnpm", ["run", "dev", "--", "--port", "4101"]))

    def test_each_project_gets_its_own_preview(self):
        for name in ("tienda", "blog"):
            path = Path(self.tmp.name) / name
            path.mkdir()
            # A tiny dev server: prints its URL and stays up.
            (path / "package.json").write_text(json.dumps({"scripts": {"dev": "x"}}))
        original = runner.program
        runner.program = lambda name, *args: ["python3", "-u", "-c",
                                               "import sys,time; print('Local: http://localhost:' + sys.argv[-1]); time.sleep(60)",
                                               *args]
        try:
            a = self.projects.handle({"action": "run", "name": "tienda"})
            b = self.projects.handle({"action": "run", "name": "blog"})
            self.assertEqual((a["url"], b["url"]), ("http://tienda.dev.finnip", "http://blog.dev.finnip"))
            ports = [port for _, port in self.routes]
            self.assertEqual(len(set(ports)), 2)
            self.projects.handle({"action": "stop", "name": "tienda"})
            self.assertEqual(self.routes[-1], ("tienda", None))
            self.projects.handle({"action": "stop", "name": "blog"})
        finally:
            runner.program = original


if __name__ == "__main__":
    unittest.main()
