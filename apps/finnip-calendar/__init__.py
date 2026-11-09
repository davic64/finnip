"""iCloud calendar for Finnip over CalDAV: list, create and delete events.

Plain CalDAV with the standard library (no caldav/icalendar packages in the Hermes image).
Credentials come from the environment: ICLOUD_USER (Apple ID), ICLOUD_APP_PASSWORD (an
app-specific password) and CALDAV_CALENDAR_URL (the calendar collection, found once by discovery).
The voice gateway imports this file too (read only mount) to show the agenda panel.
"""
import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

TZ_NAME = "America/Mexico_City"
TZ = ZoneInfo(TZ_NAME)
# Mexico City has had no DST since 2022: one fixed offset is the whole zone definition.
VTIMEZONE = ["BEGIN:VTIMEZONE", f"TZID:{TZ_NAME}", "BEGIN:STANDARD", "DTSTART:19700101T000000",
             "TZOFFSETFROM:-0600", "TZOFFSETTO:-0600", "TZNAME:CST", "END:STANDARD", "END:VTIMEZONE"]
RRULE = re.compile(r"FREQ=(DAILY|WEEKLY|MONTHLY|YEARLY)(;[A-Z]+=[A-Z0-9,+\-]+)*")
ACTIONS = ("list", "create", "delete")
DEFAULT_MINUTES = 30
MAX_EVENTS = 25
NS = {"D": "DAV:", "C": "urn:ietf:params:xml:ns:caldav"}

SCHEMA = {
    "name": "finnip_calendar",
    "description": (
        "Calendario de iCloud del usuario (zona America/Mexico_City). "
        "list: eventos entre from y to (por defecto, los próximos 7 días). "
        "create: agenda un evento; úsalo también para los recordatorios personales del usuario "
        "(un evento con reminder_minutes avisa en su iPhone y su Mac). "
        "delete: borra un evento por event_id (obtenlo con list). "
        "Fechas en ISO local sin zona, por ejemplo 2026-11-10T08:00; una fecha sola (2026-11-10) es de día completo."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": list(ACTIONS)},
            "from": {"type": "string", "description": "list: inicio del rango (ISO local). Por defecto, ahora"},
            "to": {"type": "string", "description": "list: fin del rango (ISO local). Por defecto, from + 7 días"},
            "summary": {"type": "string", "description": "create: título del evento"},
            "start": {"type": "string", "description": "create: inicio (ISO local) o fecha de día completo"},
            "end": {"type": "string", "description": f"create: fin. Por defecto, start + {DEFAULT_MINUTES} min o un día completo"},
            "description": {"type": "string", "description": "create: notas opcionales"},
            "reminder_minutes": {
                "type": "integer", "minimum": 0, "maximum": 40320,
                "description": "create: aviso N minutos antes (0 = a la hora). Sin él, sin aviso propio",
            },
            "repeat": {
                "type": "string",
                "description": ("create: repetición como regla RRULE de iCalendar, por ejemplo FREQ=WEEKLY;BYDAY=WE, "
                                "FREQ=DAILY;COUNT=10, FREQ=MONTHLY;BYMONTHDAY=1 o FREQ=WEEKLY;UNTIL=20261231T235959Z. "
                                "Omítelo si no se repite"),
            },
            "event_id": {"type": "string", "description": "delete: id del evento (de list); en un evento repetido borra toda la serie"},
        },
        "required": ["action"],
    },
}


# --- CalDAV over HTTP ---------------------------------------------------------------------------
def calendar_url():
    url = os.environ.get("CALDAV_CALENDAR_URL", "")
    if not (url and os.environ.get("ICLOUD_USER") and os.environ.get("ICLOUD_APP_PASSWORD")):
        raise RuntimeError("El calendario de iCloud no está configurado en el servidor")
    return url if url.endswith("/") else url + "/"


def request(method, url, body=None, headers=None):
    auth = f"{os.environ['ICLOUD_USER']}:{os.environ['ICLOUD_APP_PASSWORD']}".encode()
    req = urllib.request.Request(url, data=body.encode() if body else None, method=method,
                                 headers={"Authorization": "Basic " + base64.b64encode(auth).decode(), **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"iCloud respondió HTTP {error.code}") from error
    except urllib.error.URLError as error:
        raise RuntimeError("No se pudo conectar con iCloud") from error


def utc(moment):
    return moment.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def as_datetime(moment):
    return moment if isinstance(moment, datetime) else datetime.combine(moment, datetime.min.time(), TZ)


# --- iCalendar (just what Finnip needs) -------------------------------------------------------
def unescape(text):
    return re.sub(r"\\([\\,;nN])", lambda m: "\n" if m.group(1) in "nN" else m.group(1), text)


def escape(text):
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def ics_time(params, value):
    """DTSTART/DTEND value -> date (all-day) or datetime in Mexico City."""
    if params.get("VALUE") == "DATE" or len(value) == 8:
        return date(int(value[:4]), int(value[4:6]), int(value[6:8]))
    moment = datetime.strptime(value.rstrip("Z"), "%Y%m%dT%H%M%S")
    if value.endswith("Z"):
        return moment.replace(tzinfo=timezone.utc).astimezone(TZ)
    try:
        zone = ZoneInfo(params["TZID"]) if params.get("TZID") else TZ
    except Exception:  # an unknown TZID (Windows names): assume local time
        zone = TZ
    return moment.replace(tzinfo=zone).astimezone(TZ)


def vevents(ics):
    """Every VEVENT as {"SUMMARY"|"DTSTART"|"DTEND"|"UID": (params, value)}; nested VALARMs ignored."""
    events, current, depth = [], None, 0
    for line in re.sub(r"\r?\n[ \t]", "", ics).splitlines():
        if line == "BEGIN:VEVENT":
            current, depth = {}, 0
        elif line == "END:VEVENT" and current is not None:
            events.append(current)
            current = None
        elif current is not None:
            if line.startswith("BEGIN:"):
                depth += 1
            elif line.startswith("END:"):
                depth -= 1
            elif depth == 0 and ":" in line:
                head, value = line.split(":", 1)
                name, *params = head.split(";")
                if name in ("SUMMARY", "DTSTART", "DTEND", "UID"):
                    current[name] = (dict(p.split("=", 1) for p in params if "=" in p), value)
    return events


def brief(event, href):
    start = ics_time(*event["DTSTART"])
    end = ics_time(*event["DTEND"]) if "DTEND" in event else start
    return {"id": href, "summary": unescape(event.get("SUMMARY", ({}, "(sin título)"))[1]),
            "start": start.isoformat(), "end": end.isoformat(), "all_day": not isinstance(start, datetime)}


def list_events(start, end, limit=MAX_EVENTS):
    """Events overlapping [start, end), soonest first; recurring ones expanded by the server."""
    s, e = utc(as_datetime(start)), utc(as_datetime(end))
    body = f"""<?xml version="1.0" encoding="utf-8"?>
<C:calendar-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:prop><C:calendar-data><C:expand start="{s}" end="{e}"/></C:calendar-data></D:prop>
  <C:filter><C:comp-filter name="VCALENDAR"><C:comp-filter name="VEVENT">
    <C:time-range start="{s}" end="{e}"/>
  </C:comp-filter></C:comp-filter></C:filter>
</C:calendar-query>"""
    xml = request("REPORT", calendar_url(), body, {"Depth": "1", "Content-Type": "application/xml; charset=utf-8"})
    found = []
    for response in ET.fromstring(xml).iterfind("D:response", NS):
        href = response.findtext("D:href", "", NS)
        data = response.findtext(".//C:calendar-data", "", NS)
        found += [brief(ev, href) for ev in vevents(data) if "DTSTART" in ev]
    lo, hi = as_datetime(start), as_datetime(end)
    # Keep what overlaps the range. ponytail: a server that ignores <expand> returns a recurring
    # event's first date, dropped here when out of range. Upgrade: expand RRULE locally.
    found = [ev for ev in found if moment(ev["start"]) < hi and max(moment(ev["end"]), moment(ev["start"])) >= lo]
    found.sort(key=lambda ev: moment(ev["start"]))
    return found[:limit]


def moment(iso):
    return as_datetime(datetime.fromisoformat(iso) if "T" in iso else date.fromisoformat(iso))


def event_ics(params):
    summary = (params.get("summary") or "").strip()
    if not summary or not params.get("start"):
        raise ValueError("create necesita summary y start")
    start = parse_time(params["start"])
    if params.get("end"):
        end = parse_time(params["end"])
    else:
        end = start + (timedelta(minutes=DEFAULT_MINUTES) if isinstance(start, datetime) else timedelta(days=1))
    if type(start) is not type(end):
        raise ValueError("start y end deben ser ambos fecha y hora, o ambos solo fecha")
    if end <= start:
        raise ValueError("end debe ser posterior a start")
    rule = (params.get("repeat") or "").strip().upper().removeprefix("RRULE:")
    if rule and not RRULE.fullmatch(rule):
        raise ValueError("repeat debe ser una regla RRULE, por ejemplo FREQ=WEEKLY;BYDAY=WE")
    timed = isinstance(start, datetime)
    # Local time with TZID (not UTC): a weekly rule must repeat on the local weekday.
    when = (lambda m: f";TZID={TZ_NAME}:{m.astimezone(TZ):%Y%m%dT%H%M%S}") if timed else (lambda d: f";VALUE=DATE:{d:%Y%m%d}")
    uid = str(uuid.uuid4())
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Finnip//ES"] + (VTIMEZONE if timed else [])
    lines += ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{utc(datetime.now(timezone.utc))}",
              f"DTSTART{when(start)}", f"DTEND{when(end)}", f"SUMMARY:{escape(summary)}"]
    if rule:
        lines.append(f"RRULE:{rule}")
    if params.get("description"):
        lines.append(f"DESCRIPTION:{escape(params['description'])}")
    if params.get("reminder_minutes") is not None:
        lines += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{escape(summary)}",
                  f"TRIGGER:-PT{int(params['reminder_minutes'])}M", "END:VALARM"]
    lines += ["END:VEVENT", "END:VCALENDAR"]
    # ponytail: no 75-octet line folding; iCloud accepts long lines. Fold if another server rejects them.
    return uid, "\r\n".join(lines) + "\r\n", start, end, summary


def parse_time(value):
    """ISO local time -> aware datetime in Mexico City; a bare date -> date (all-day)."""
    value = value.strip()
    if len(value) == 10:
        return date.fromisoformat(value)
    moment = datetime.fromisoformat(value)
    return moment.replace(tzinfo=TZ) if moment.tzinfo is None else moment.astimezone(TZ)


def run(params):
    action = params.get("action")
    if action not in ACTIONS:
        raise ValueError(f"action debe ser una de: {', '.join(ACTIONS)}")
    if action == "list":
        start = parse_time(params["from"]) if params.get("from") else datetime.now(TZ)
        end = parse_time(params["to"]) if params.get("to") else as_datetime(start) + timedelta(days=7)
        return list_events(start, end)
    if action == "create":
        uid, ics, start, end, summary = event_ics(params)
        href = urllib.parse.urlparse(calendar_url()).path + f"{uid}.ics"
        request("PUT", urllib.parse.urljoin(calendar_url(), href), ics,
                {"Content-Type": "text/calendar; charset=utf-8", "If-None-Match": "*"})
        return {"id": href, "summary": summary, "start": start.isoformat(), "end": end.isoformat()}
    event_id = params.get("event_id") or ""
    if not event_id.endswith(".ics"):
        raise ValueError("delete necesita el event_id que devuelve list")
    request("DELETE", urllib.parse.urljoin(calendar_url(), event_id))
    return {"deleted": event_id}


def handle(params, **kwargs):
    try:
        result = run(params)
        return json.dumps({"success": True, "action": params.get("action"), "result": result}, ensure_ascii=False)
    except Exception as error:
        return json.dumps({"success": False, "error": str(error)}, ensure_ascii=False)


def register(ctx):
    ctx.register_tool(name="finnip_calendar", toolset="finnip_calendar", schema=SCHEMA, handler=handle)
