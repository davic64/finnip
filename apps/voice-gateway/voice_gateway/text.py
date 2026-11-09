"""Pure text helpers: sentence splitting, what the user heard, echo detection."""
import difflib
import re
import unicodedata

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
