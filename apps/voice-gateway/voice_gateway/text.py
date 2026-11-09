"""Pure text helpers: sentence splitting, what the user heard, echo detection."""
import difflib
import re
import unicodedata
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

SENTENCE_END = re.compile(r"(?<=[.!?:;])\s+")
FIRST_CLAUSE_END = re.compile(r"(?<=,)\s+")
MAX_SENTENCE = 200
MIN_FIRST_CLAUSE = 30  # the first chunk may end at a comma, so audio starts before the sentence ends
# ponytail: fixed speech rate to estimate a cut sentence; measure Edge's real rate if the cut point matters.
SECONDS_PER_WORD = 0.35
ECHO_SIMILARITY = 0.6


class SentenceSplitter:
    """Feed streamed text, get complete sentences back as soon as they close."""

    def __init__(self):
        self.buffer = ""
        self.started = False

    def feed(self, delta):
        self.buffer += delta
        parts = SENTENCE_END.split(self.buffer)
        self.buffer = parts.pop()
        out = [p.strip() for p in parts if p.strip()]
        if not self.started and not out:
            for m in FIRST_CLAUSE_END.finditer(self.buffer):
                if m.start() >= MIN_FIRST_CLAUSE:
                    out.append(self.buffer[:m.start()].strip())
                    self.buffer = self.buffer[m.end():]
                    break
        self.started = self.started or bool(out)
        while len(self.buffer) > MAX_SENTENCE:
            cut = self.buffer.rfind(" ", 0, MAX_SENTENCE)
            cut = cut if cut > 0 else MAX_SENTENCE
            out.append(self.buffer[:cut].strip())
            self.buffer = self.buffer[cut:].lstrip()
        return out

    def flush(self):
        rest, self.buffer = self.buffer.strip(), ""
        return [rest] if rest else []


def heard_text(sentences, played_seq, played_ms):
    """Text the user actually heard: sentences before played_seq, plus the start of the cut one."""
    heard = list(sentences[:played_seq])
    if played_seq < len(sentences):
        words = sentences[played_seq].split()
        n = min(len(words), int(played_ms / 1000 / SECONDS_PER_WORD))
        if n:
            heard.append(" ".join(words[:n]) + "…")
    return " ".join(heard)


def with_heard_note(user_text, heard):
    if heard is None:
        return user_text
    return (f'[El usuario interrumpió tu respuesta anterior; solo alcanzó a oír: "{heard}". '
            f"No des por dicho lo demás.]\n\n{user_text}")


def _norm(text):
    text = unicodedata.normalize("NFKD", text.casefold())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^\w ]", " ", text).split())


def is_echo(transcript, spoken):
    """True when the barge-in transcript is Finnip's own voice picked up by the mic."""
    t = _norm(transcript)
    if not t:
        return True
    s = _norm(" ".join(spoken))
    if t in s:
        return True
    return difflib.SequenceMatcher(None, t, s).find_longest_match().size / len(t) >= ECHO_SIMILARITY


# ponytail: keyword match; "memoria" can also mean conversation memory. Move to an intent call if it misfires.
STATS_WORDS = {"servidor", "server", "ram", "memoria", "cpu", "procesador", "disco", "almacenamiento"}


def wants_stats(text):
    return bool(STATS_WORDS & set(_norm(text).split()))


def stats_note(s, user_text):
    days, rest = divmod(s["uptime"], 86400)
    temp = f", temperatura {s['temp']} °C" if s["temp"] is not None else ""
    return (f"[Estado real del servidor medido ahora mismo: CPU {s['cpu']} % ({s['cores']} núcleos, carga "
            f"{s['load']}), RAM {s['ram_used']} de {s['ram_total']} GB, disco {s['disk_used']} de "
            f"{s['disk_total']} GB{temp}, encendido hace {days} días y {rest // 3600} horas. "
            f"La pantalla ya muestra estos números: usa estos datos y no ejecutes comandos para medirlos.]"
            f"\n\n{user_text}")


# ponytail: keyword match; a phrase that also creates or cancels one goes to Hermes without the panel.
REMINDER_WORDS = {"recordatorio", "recordatorios", "alarma", "alarmas", "calendario", "evento", "eventos", "agenda"}
REMINDER_CHANGES = {"pon", "ponme", "crea", "creame", "agrega", "agregame", "anade", "programa", "programame",
                    "cancela", "borra", "elimina", "quita", "cambia", "mueve", "pospon", "agendame", "agendalo",
                    "agendar", "recuerdame", "recuerdamelo"}
RANGE_WORDS = {"hoy", "manana", "semana", "mes", "ano"}
def wants_reminders(text):
    words = _norm(text).split()
    if not words or words[0] == "agenda" or REMINDER_CHANGES & set(words):
        return False
    return bool(REMINDER_WORDS & set(words)) or ("tengo" in words and bool(RANGE_WORDS & set(words)))
TZ = ZoneInfo("America/Mexico_City")
DAYS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
def calendar_items(events, now=None):
    """finnip-calendar events (sorted by start) as [{"name", "when", "date", "day", "time"}] in Mexico City
    time; "when" is for Hermes, the rest lets the UI group by day. "time" is "" for all-day events."""
    today = (now or datetime.now(TZ)).astimezone(TZ).date()
    def day(d):
        days = (d - today).days
        return "Hoy" if days == 0 else "Mañana" if days == 1 else f"{DAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]}"
    items = []
    for event in events:
        if event.get("all_day"):
            on, clock = date.fromisoformat(event["start"]), ""
        else:
            at = datetime.fromisoformat(event["start"]).astimezone(TZ)
            on, clock = at.date(), f"{at:%H:%M}"
        label = day(on)
        items.append({"name": event.get("summary") or "Sin título", "when": f"{label} · {clock or 'todo el día'}",
                      "date": on.isoformat(), "day": label, "time": clock})
    return items
def agenda_range(text, now=None):
    """(label, start, end) of the period the phrase asks about; the next 7 days by default."""
    now = (now or datetime.now(TZ)).astimezone(TZ)
    words = set(_norm(text).split())
    today = datetime.combine(now.date(), time(), TZ)
    upcoming = bool({"proxima", "proximo", "siguiente"} & words)
    next_month = lambda d: (d.replace(day=1) + timedelta(days=32)).replace(day=1)  # noqa: E731
    if "ano" in words:
        year = datetime(now.year + 1, 1, 1, tzinfo=TZ)
        return ("Próximo año", year, year.replace(year=year.year + 1)) if upcoming else ("Este año", now, year)
    if "mes" in words:
        month = next_month(today)
        return ("Próximo mes", month, next_month(month)) if upcoming else ("Este mes", now, month)
    if "semana" in words:
        monday = today + timedelta(days=7 - today.weekday())
        return ("Próxima semana", monday, monday + timedelta(days=7)) if upcoming else ("Esta semana", now, monday)
    if "hoy" in words:  # before "mañana": "hoy en la mañana" is today
        return "Hoy", now, today + timedelta(days=1)
    if "manana" in words:
        return "Mañana", today + timedelta(days=1), today + timedelta(days=2)
    return "Próximos 7 días", now, now + timedelta(days=7)
def reminders_note(items, user_text, label="Próximos 7 días"):
    listed = "; ".join(f"{i['name']} ({i['when']})" for i in items) or "ninguno"
    return (f"[Eventos del calendario de iCloud del usuario para el periodo «{label}», leídos ahora mismo: "
            f"{listed}. La pantalla ya los muestra. Si el usuario pidió exactamente este periodo, responde con estos "
            f"datos sin llamar herramientas; si pidió otro periodo o fecha, consulta finnip_calendar con ese rango.]"
            f"\n\n{user_text}")
WAKE_WORD = "finnip"
WAKE_LEADS = {"oye", "hey", "ey", "ok", "okay"}
# How Parakeet writes the user's "Finnip" (logged 2026-11-09): "Finip", and "Philip" when said alone.
WAKE_VARIANTS = {"philip", "phillip", "felip", "finip", "finny", "fini"}
WAKE_TOKEN = re.compile(r"[^\s,.;:¿?¡!]+")


# ponytail: fuzzy match on Parakeet's transcript ("Finny", "Cinip", "FinNip"); the lone word is often
# misheard ("Thing"), so it works best followed by the order. Upgrade: a real wake-word model
# (Porcupine or a custom openWakeWord) in the browser.
def after_wake_word(text):
    """The order after "Finnip" when the phrase starts with it ("" if nothing follows), else None."""
    for i, m in enumerate(WAKE_TOKEN.finditer(text)):
        word = _norm(m.group()).replace(" ", "")
        if word in WAKE_VARIANTS or (len(word) >= 4 and difflib.SequenceMatcher(None, word, WAKE_WORD).ratio() >= 0.6):
            return text[m.end():].lstrip(" ,.;:!").strip()
        if i >= 1 or word not in WAKE_LEADS:
            return None
    return None
