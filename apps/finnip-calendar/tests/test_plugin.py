import importlib.util
import json
import unittest
from pathlib import Path

# The plugin directory name has a hyphen, so load __init__.py by path.
spec = importlib.util.spec_from_file_location("finnip_calendar", Path(__file__).parent.parent / "__init__.py")
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)


class FakeCall:
    def __init__(self, result):
        self.result = result

    def execute(self):
        return self.result


class FakeEvents:
    def __init__(self):
        self.calls = []

    def list(self, **kw):
        self.calls.append(("list", kw))
        return FakeCall({"items": [{"id": "e1", "summary": "Dentista",
                                    "start": {"dateTime": "2026-11-10T09:00:00-06:00"},
                                    "end": {"dateTime": "2026-11-10T10:00:00-06:00"}}]})

    def insert(self, **kw):
        self.calls.append(("insert", kw))
        return FakeCall({"id": "new", **kw["body"]})

    def delete(self, **kw):
        self.calls.append(("delete", kw))
        return FakeCall("")


class FakeApi:
    def __init__(self):
        self.fake = FakeEvents()

    def events(self):
        return self.fake


class CalendarTest(unittest.TestCase):
    def setUp(self):
        self.api = FakeApi()

    def run_action(self, params):
        return plugin.run(params, api=self.api)

    def test_list_uses_local_range(self):
        result = self.run_action({"action": "list", "from": "2026-11-10", "to": "2026-11-11"})
        self.assertEqual(result, [{"id": "e1", "summary": "Dentista", "start": "2026-11-10T09:00:00-06:00",
                                   "end": "2026-11-10T10:00:00-06:00", "all_day": False}])
        kw = self.api.fake.calls[0][1]
        self.assertEqual((kw["timeMin"], kw["timeMax"]), ("2026-11-10T00:00:00-06:00", "2026-11-11T00:00:00-06:00"))
        self.assertTrue(kw["singleEvents"])

    def test_create_reminder_defaults_to_30_minutes_with_popup(self):
        self.run_action({"action": "create", "summary": "Pagar luz", "start": "2026-11-10T08:00",
                         "reminder_minutes": 0})
        body = self.api.fake.calls[0][1]["body"]
        self.assertEqual(body["start"], {"dateTime": "2026-11-10T08:00:00-06:00", "timeZone": "America/Mexico_City"})
        self.assertEqual(body["end"]["dateTime"], "2026-11-10T08:30:00-06:00")
        self.assertEqual(body["reminders"], {"useDefault": False, "overrides": [{"method": "popup", "minutes": 0}]})

    def test_create_all_day(self):
        self.run_action({"action": "create", "summary": "Viaje", "start": "2026-11-20"})
        body = self.api.fake.calls[0][1]["body"]
        self.assertEqual((body["start"], body["end"]), ({"date": "2026-11-20"}, {"date": "2026-11-21"}))
        self.assertNotIn("reminders", body)

    def test_bad_input_is_an_error_not_a_call(self):
        for params in ({"action": "create", "summary": "x"},
                       {"action": "create", "summary": "x", "start": "2026-11-10T08:00", "end": "2026-11-10T07:00"},
                       {"action": "create", "summary": "x", "start": "2026-11-10", "end": "2026-11-10T09:00"},
                       {"action": "delete"},
                       {"action": "move"}):
            with self.assertRaises(ValueError):
                self.run_action(params)
        self.assertEqual(self.api.fake.calls, [])

    def test_handle_reports_errors_as_json(self):
        out = json.loads(plugin.handle({"action": "move"}))
        self.assertFalse(out["success"])


if __name__ == "__main__":
    unittest.main()
