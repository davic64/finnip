"""Google Calendar for Finnip: list, create and delete events on the user's primary calendar.

Runs inside Hermes, where the OAuth token lives (HERMES_HOME/google_token.json, calendar scope
only). The terminal tool runs on the host as another user and cannot read that token.
"""
import json
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

TZ_NAME = "America/Mexico_City"
TZ = ZoneInfo(TZ_NAME)
TOKEN = os.path.join(os.environ.get("HERMES_HOME", "/opt/data"), "google_token.json")
ACTIONS = ("list", "create", "delete")
DEFAULT_MINUTES = 30
MAX_EVENTS = 25

SCHEMA = {
    "name": "finnip_calendar",
    "description": (
        "Google Calendar del usuario (calendario principal, zona America/Mexico_City). "
        "list: eventos entre from y to (por defecto, los próximos 7 días). "
        "create: agenda un evento; úsalo también para los recordatorios personales del usuario "
        "(un evento con reminder_minutes avisa en su teléfono). "
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
                "description": "create: aviso emergente N minutos antes (0 = a la hora). Sin él, el aviso por defecto del calendario",
            },
            "event_id": {"type": "string", "description": "delete: id del evento"},
        },
        "required": ["action"],
    },
}


def service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    if not os.path.exists(TOKEN):
        raise RuntimeError("Google Calendar no está autorizado en el servidor")
    creds = Credentials.from_authorized_user_file(TOKEN)
    # ponytail: refresh in memory on every call (an extra token request per call); persist the
    # refreshed token if call volume ever matters.
    if not creds.valid:
        creds.refresh(Request())
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def parse_time(value):
    """ISO local time -> aware datetime in Mexico City; a bare date -> date (all-day)."""
    value = value.strip()
    if len(value) == 10:
        return date.fromisoformat(value)
    moment = datetime.fromisoformat(value)
    return moment.replace(tzinfo=TZ) if moment.tzinfo is None else moment.astimezone(TZ)


def as_google(moment):
    if isinstance(moment, datetime):
        return {"dateTime": moment.isoformat(), "timeZone": TZ_NAME}
    return {"date": moment.isoformat()}


def event_body(params):
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
    body = {"summary": summary, "start": as_google(start), "end": as_google(end)}
    if params.get("description"):
        body["description"] = params["description"]
    if params.get("reminder_minutes") is not None:
        minutes = int(params["reminder_minutes"])
        body["reminders"] = {"useDefault": False, "overrides": [{"method": "popup", "minutes": minutes}]}
    return body


def brief(event):
    start, end = event.get("start", {}), event.get("end", {})
    return {
        "id": event.get("id"),
        "summary": event.get("summary", "(sin título)"),
        "start": start.get("dateTime") or start.get("date"),
        "end": end.get("dateTime") or end.get("date"),
        "all_day": "date" in start,
    }


def run(params, api=None):
    action = params.get("action")
    if action not in ACTIONS:
        raise ValueError(f"action debe ser una de: {', '.join(ACTIONS)}")
    events = (api or service()).events()
    if action == "list":
        start = parse_time(params["from"]) if params.get("from") else datetime.now(TZ)
        end = parse_time(params["to"]) if params.get("to") else start + timedelta(days=7)
        to_dt = lambda m: m if isinstance(m, datetime) else datetime.combine(m, datetime.min.time(), TZ)  # noqa: E731
        found = events.list(calendarId="primary", timeMin=to_dt(start).isoformat(), timeMax=to_dt(end).isoformat(),
                            singleEvents=True, orderBy="startTime", maxResults=MAX_EVENTS).execute()
        return [brief(e) for e in found.get("items", [])]
    if action == "create":
        return brief(events.insert(calendarId="primary", body=event_body(params)).execute())
    if not params.get("event_id"):
        raise ValueError("delete necesita event_id")
    events.delete(calendarId="primary", eventId=params["event_id"]).execute()
    return {"deleted": params["event_id"]}


def handle(params, **kwargs):
    try:
        result = run(params)
        return json.dumps({"success": True, "action": params.get("action"), "result": result}, ensure_ascii=False)
    except Exception as error:
        return json.dumps({"success": False, "error": str(error)}, ensure_ascii=False)


def register(ctx):
    ctx.register_tool(name="finnip_calendar", toolset="finnip_calendar", schema=SCHEMA, handler=handle)
