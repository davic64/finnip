import importlib.util
import json
import os
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

# The plugin directory name has a hyphen, so load __init__.py by path.
spec = importlib.util.spec_from_file_location("finnip_calendar", Path(__file__).parent.parent / "__init__.py")
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)

ENV = {"ICLOUD_USER": "yo@icloud.com", "ICLOUD_APP_PASSWORD": "abcd-efgh-ijkl-mnop",
       "CALDAV_CALENDAR_URL": "https://p1-caldav.icloud.com/123/calendars/home/"}

REPORT = """<?xml version="1.0"?>
<D:multistatus xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
 <D:response><D:href>/123/calendars/home/a.ics</D:href><D:propstat><D:prop><C:calendar-data>BEGIN:VCALENDAR
BEGIN:VEVENT
UID:a
DTSTART;TZID=America/Mexico_City:20261110T183000
DTEND;TZID=America/Mexico_City:20261110T193000
SUMMARY:Junta\\, seguros
BEGIN:VALARM
DESCRIPTION:no es el título
END:VALARM
END:VEVENT
END:VCALENDAR
</C:calendar-data></D:prop></D:propstat></D:response>
 <D:response><D:href>/123/calendars/home/b.ics</D:href><D:propstat><D:prop><C:calendar-data>BEGIN:VCALENDAR
BEGIN:VEVENT
UID:b
DTSTART;VALUE=DATE:20261110
DTEND;VALUE=DATE:20261111
SUMMARY:Iglesia
END:VEVENT
BEGIN:VEVENT
UID:c
DTSTART:20261109T120000Z
DTEND:20261109T130000Z
SUMMARY:Ya pasó
END:VEVENT
END:VCALENDAR
</C:calendar-data></D:prop></D:propstat></D:response>
</D:multistatus>"""


@mock.patch.dict(os.environ, ENV)
class CalendarTest(unittest.TestCase):
    def fake(self, reply=""):
        self.sent = []

        def request(method, url, body=None, headers=None):
            self.sent.append((method, url, body, headers))
            return reply
        return mock.patch.object(plugin, "request", request)

    def test_list_parses_sorts_and_drops_past_events(self):
        with self.fake(REPORT):
            got = plugin.list_events(datetime.fromisoformat("2026-11-10T00:00:00-06:00"),
                                     datetime.fromisoformat("2026-11-17T00:00:00-06:00"))
        self.assertEqual(got, [
            {"id": "/123/calendars/home/b.ics", "summary": "Iglesia", "start": "2026-11-10",
             "end": "2026-11-11", "all_day": True},
            {"id": "/123/calendars/home/a.ics", "summary": "Junta, seguros", "start": "2026-11-10T18:30:00-06:00",
             "end": "2026-11-10T19:30:00-06:00", "all_day": False},
        ])
        method, url, body, headers = self.sent[0]
        self.assertEqual((method, url, headers["Depth"]), ("REPORT", ENV["CALDAV_CALENDAR_URL"], "1"))
        self.assertIn('<C:time-range start="20261110T060000Z" end="20261117T060000Z"/>', body)

    def test_create_puts_utc_event_with_alarm(self):
        with self.fake():
            out = plugin.run({"action": "create", "summary": "Pagar luz, agua", "start": "2026-11-10T08:00",
                              "reminder_minutes": 0})
        method, url, body, headers = self.sent[0]
        self.assertEqual((method, headers["If-None-Match"]), ("PUT", "*"))
        self.assertTrue(url.startswith(ENV["CALDAV_CALENDAR_URL"]) and url.endswith(".ics"))
        self.assertEqual(out["id"], url.removeprefix("https://p1-caldav.icloud.com"))
        for line in ("DTSTART:20261110T140000Z", "DTEND:20261110T143000Z", "SUMMARY:Pagar luz\\, agua",
                     "TRIGGER:-PT0M"):
            self.assertIn(line + "\r\n", body)

    def test_create_all_day_without_alarm(self):
        with self.fake():
            plugin.run({"action": "create", "summary": "Viaje", "start": "2026-11-20"})
        body = self.sent[0][2]
        self.assertIn("DTSTART;VALUE=DATE:20261120\r\n", body)
        self.assertIn("DTEND;VALUE=DATE:20261121\r\n", body)
        self.assertNotIn("VALARM", body)

    def test_delete_uses_the_listed_href(self):
        with self.fake():
            plugin.run({"action": "delete", "event_id": "/123/calendars/home/a.ics"})
        self.assertEqual(self.sent[0][:2], ("DELETE", "https://p1-caldav.icloud.com/123/calendars/home/a.ics"))

    def test_bad_input_is_an_error_not_a_call(self):
        with self.fake():
            for params in ({"action": "create", "summary": "x"},
                           {"action": "create", "summary": "x", "start": "2026-11-10T08:00", "end": "2026-11-10T07:00"},
                           {"action": "create", "summary": "x", "start": "2026-11-10", "end": "2026-11-10T09:00"},
                           {"action": "delete", "event_id": "../../otro"},
                           {"action": "move"}):
                with self.assertRaises(ValueError):
                    plugin.run(params)
        self.assertEqual(self.sent, [])

    def test_missing_credentials_is_a_clear_error(self):
        with mock.patch.dict(os.environ, {"ICLOUD_APP_PASSWORD": ""}):
            out = json.loads(plugin.handle({"action": "list"}))
        self.assertEqual(out, {"success": False, "error": "El calendario de iCloud no está configurado en el servidor"})


if __name__ == "__main__":
    unittest.main()
