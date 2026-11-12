import difflib
import json
import os
import re
import unicodedata
import urllib.error
import urllib.request

BRIDGE_URL = os.environ.get("FINNIP_BRIDGE_URL", "http://home-bridge:3000").rstrip("/")

ACTIONS = (
    "list", "status", "on", "off", "brightness", "color", "color_temp",
    "open", "close", "stop", "position", "temperature", "hvac_mode",
    "play", "command", "pause", "resume", "volume", "run",
    "discover", "expose", "hide", "modes", "mode", "save_mode", "delete_mode",
)
# Parameters each action forwards to Home Bridge, which validates them again.
ACTION_FIELDS = {
    "brightness": ("brightness",),
    "color": ("rgb", "brightness"),
    "color_temp": ("kelvin", "brightness"),
    "position": ("position",),
    "temperature": ("temperature",),
    "hvac_mode": ("hvac_mode",),
    "play": ("query",),
    "command": ("text",),
    "volume": ("volume",),
}
ENTITY_ID = re.compile(r"^[a-z_]+\.[a-z0-9_]+$")


def call_bridge(method, path, body=None):
    api_key = os.environ.get("BRIDGE_API_KEY")
    if not api_key:
        raise RuntimeError("BRIDGE_API_KEY no está configurada")

    payload = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url=f"{BRIDGE_URL}{path}",
        data=payload,
        method=method,
        headers={"Authorization": f"Bearer {api_key}"},
    )
    # Fastify rejects an empty body declared as JSON (FST_ERR_CTP_EMPTY_JSON_BODY).
    if payload is not None:
        request.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        # Home Bridge errors are short and generic, safe to show to the model.
        try:
            detail = json.loads(error.read().decode("utf-8")).get("error")
        except (ValueError, AttributeError):
            detail = None
        suffix = f": {detail}" if detail else ""
        raise RuntimeError(f"Home Bridge devolvió HTTP {error.code}{suffix}") from error
    except urllib.error.URLError as error:
        raise RuntimeError("No se pudo conectar con Home Bridge") from error


def normalize(text):
    text = unicodedata.normalize("NFKD", text.casefold())
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).split())


def resolve_device(device, path="/devices", key="devices"):
    """Accept an entity_id or a device name, so the model can act without a prior list call.
    expose looks the name up among the candidates instead, since the device is not exposed yet."""
    if ENTITY_ID.match(device):
        return device
    query = normalize(device)
    if not query:
        raise ValueError("Falta el dispositivo: usa su nombre o su id")
    devices = call_bridge("GET", path).get(key, [])
    names = {d["id"]: normalize(d.get("name", "")) for d in devices}
    exact = [id_ for id_, name in names.items() if name == query]
    partial = [id_ for id_, name in names.items() if name and (query in name or name in query)]
    matches = exact or partial
    if len(matches) == 1:
        return matches[0]
    available = ", ".join(d.get("name", d["id"]) for d in devices) or "ninguno"
    problem = "es ambiguo" if matches else "no coincide con ningún dispositivo"
    raise ValueError(f"'{device}' {problem}. Disponibles: {available}")


def slugify(name):
    """'Modo Lectura Nocturna' -> 'lectura_nocturna': the bridge script is always modo_<slug>."""
    words = normalize(name).split()
    if words[:1] == ["modo"]:
        words = words[1:]
    slug = re.sub(r"[^a-z0-9]+", "_", " ".join(words)).strip("_")[:40]
    if not slug:
        raise ValueError("Falta el nombre del modo")
    return slug


def mode_action(action, params):
    slug = slugify(str(params.get("name") or ""))
    if action == "mode":
        return call_bridge("GET", f"/modes/{slug}")
    if action == "delete_mode":
        return call_bridge("DELETE", f"/modes/{slug}")
    steps = params.get("steps")
    if not isinstance(steps, list) or not steps or not all(isinstance(step, dict) for step in steps):
        raise ValueError("Faltan los pasos del modo: lista de {device, action, params}")
    steps = [{"device": resolve_device(str(step.get("device") or "")), "action": step.get("action"),
              "params": step.get("params") or {}} for step in steps]
    body = {"name": params["name"], "music": params.get("music", True), "steps": steps}
    return call_bridge("PUT", f"/modes/{slug}", body)


def run(params):
    action = params.get("action")
    if action not in ACTIONS:
        raise ValueError("Acción no permitida")
    if action == "list":
        return call_bridge("GET", "/devices")
    if action == "discover":
        return call_bridge("GET", "/candidates")
    if action == "modes":
        return call_bridge("GET", "/modes")
    if action in ("mode", "save_mode", "delete_mode"):
        return mode_action(action, params)

    device = params.get("device")
    if not isinstance(device, str) or not device.strip():
        raise ValueError("Falta el dispositivo: usa su nombre o su id")
    device = resolve_device(device, "/candidates", "candidates") if action == "expose" else resolve_device(device)
    if action == "status":
        return call_bridge("GET", f"/devices/{device}")

    body = {field: params[field] for field in ACTION_FIELDS.get(action, ()) if field in params}
    return call_bridge("POST", f"/devices/{device}/{action}", body or None)


SCHEMA = {
    "name": "finnip_lights",
    "description": (
        "Controla los dispositivos del hogar que el usuario expuso a Finnip "
        "(luces, interruptores, persianas, climatización y bocinas Alexa). "
        "Alexa (dispositivo 'echo'): play reproduce música de Apple Music con query (canción, artista, "
        "playlist o género); command le dice a Alexa un texto como si el usuario se lo hablara, por ejemplo "
        "para crear un recordatorio o alarma en Alexa o hacerle una pregunta; pause, resume y volume (0-100). "
        "Alexa no permite compras desde Finnip. "
        "Los modos (por ejemplo 'Modo estudio', 'Modo cine') son scripts de Home Assistant: actívalos con run. "
        "Para actuar pasa directamente el nombre del dispositivo en device (por ejemplo 'lámpara'); "
        "no necesitas llamar list antes. Usa list solo para descubrir dispositivos o sus capabilities. "
        "Si el nombre no coincide o es ambiguo, el error incluye los dispositivos disponibles. "
        "Cada orden devuelve confirmed y actual con el estado que reporta Home Assistant. "
        "Gestión: discover lista los dispositivos de Home Assistant que Finnip aún no ve; expose agrega uno "
        "y hide lo oculta (solo luces, enchufes, persianas, clima y bocinas; nunca cerraduras, alarmas ni cámaras). "
        "Modos: modes los lista; mode lee uno por name; save_mode lo crea o reemplaza con name, music y steps "
        "(cada paso {device, action, params} con una acción de estado del dispositivo); delete_mode lo borra. "
        "Para cambiar un paso, lee el modo con mode, cambia ese paso y guarda todos los pasos. "
        "Un modo con editable false se editó a mano en Home Assistant: no lo sobrescribas. "
        "ANTES de expose o delete_mode nombra el dispositivo o el modo y espera un sí explícito del usuario."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": list(ACTIONS),
                "description": "list para descubrir, status para consultar, o una capability del dispositivo",
            },
            "device": {
                "type": "string",
                "description": "Nombre del dispositivo (por ejemplo 'lámpara') o su id (por ejemplo light.leds_monitores)",
            },
            "rgb": {
                "type": "array",
                "items": {"type": "integer", "minimum": 0, "maximum": 255},
                "minItems": 3,
                "maxItems": 3,
                "description": "Color RGB para color, por ejemplo [128, 0, 255]",
            },
            "kelvin": {
                "type": "integer",
                "minimum": 1000,
                "maximum": 12000,
                "description": "Temperatura de color para color_temp: ~2700 blanco cálido, ~4000 neutro, ~6500 frío",
            },
            "brightness": {
                "type": "integer",
                "minimum": 1,
                "maximum": 100,
                "description": "Brillo en porcentaje para brightness o color",
            },
            "position": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "description": "Posición de la persiana: 0 cerrada, 100 abierta",
            },
            "temperature": {
                "type": "number",
                "description": "Temperatura objetivo; respeta min_temp y max_temp del dispositivo",
            },
            "hvac_mode": {
                "type": "string",
                "description": "Uno de los hvac_modes del dispositivo, por ejemplo cool u off",
            },
            "query": {
                "type": "string",
                "maxLength": 200,
                "description": "Para play en Alexa: qué reproducir, por ejemplo 'Coldplay' o 'música para concentrarse'",
            },
            "text": {
                "type": "string",
                "maxLength": 200,
                "description": "Para command en Alexa: la frase en español tal como se la dirías a Alexa, sin decir 'Alexa'",
            },
            "volume": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "description": ("Para volume en Alexa: volumen en porcentaje. Un número del 0 al 10 sin "
                                "'por ciento' es la escala de Alexa: multiplícalo por 10 ('volumen a 3' = 30)"),
            },
            "name": {
                "type": "string",
                "maxLength": 60,
                "description": "Para mode, save_mode y delete_mode: nombre del modo, por ejemplo 'lectura'",
            },
            "music": {
                "type": "boolean",
                "description": "Para save_mode: si al activarlo Finnip pone música (por defecto true)",
            },
            "steps": {
                "type": "array",
                "maxItems": 30,
                "items": {
                    "type": "object",
                    "properties": {
                        "device": {"type": "string"},
                        "action": {"type": "string"},
                        "params": {"type": "object"},
                    },
                    "required": ["device", "action"],
                },
                "description": "Para save_mode: pasos como {device: 'lámpara', action: 'color_temp', "
                               "params: {kelvin: 2700, brightness: 40}}",
            },
        },
        "required": ["action"],
        "additionalProperties": False,
    },
}

# A step's params get the same fields as the direct actions. A bare {"type": "object"} reaches strict
# providers (OpenRouter/DeepSeek) as an object with no properties, so the model could only send {}.
_PROPS = SCHEMA["parameters"]["properties"]
_PROPS["steps"]["items"]["properties"]["params"] = {
    "type": "object",
    "properties": {field: _PROPS[field] for fields in ACTION_FIELDS.values() for field in fields},
}


def handle(params, **kwargs):
    try:
        result = run(params)
        return json.dumps({"success": True, "action": params.get("action"), "result": result}, ensure_ascii=False)
    except Exception as error:
        return json.dumps({"success": False, "error": str(error)}, ensure_ascii=False)


# Fast path: a short, unambiguous on/off order runs before the model call, so the device reacts in
# about a second instead of waiting for the LLM. Anything else (timers, "y", numbers, ambiguity)
# returns None and the model handles the message as usual.
FAST_VERBS = {
    "apaga": "off", "apagar": "off", "apague": "off", "apagame": "off",
    "prende": "on", "prender": "on", "prendeme": "on",
    "enciende": "on", "encender": "on", "enciendeme": "on",
}
COLOR_VERBS = {"pon", "ponme", "ponle", "cambia", "cambiame", "cambiale", "pinta"}
COLORS = {
    "rojo": [255, 0, 0], "roja": [255, 0, 0], "verde": [0, 255, 0], "azul": [0, 60, 255],
    "amarillo": [255, 200, 0], "amarilla": [255, 200, 0], "naranja": [255, 100, 0],
    "morado": [140, 0, 255], "morada": [140, 0, 255], "violeta": [140, 0, 255], "lila": [190, 120, 255],
    "rosa": [255, 60, 160], "rosado": [255, 60, 160], "magenta": [255, 0, 255],
    "cian": [0, 230, 255], "turquesa": [0, 255, 190], "blanco": [255, 255, 255], "blanca": [255, 255, 255],
}
COLOR_LINKS = {"en", "a", "al", "color", "de"}
ALL_LIGHTS = {"luces", "las luces", "todas las luces"}
FILLER = {"finnip", "por", "favor", "porfa", "porfavor"}
ARTICLES = {"el", "la", "los", "las", "de", "del"}


def parse_color_order(words):
    """["pon", "los", "monitores", "en", "rojo"] -> ("color", "monitores", {"rgb": [255, 0, 0]})."""
    if words[0] not in COLOR_VERBS or words[-1] not in COLORS:
        return None
    rest = words[1:-1]
    while rest and rest[-1] in COLOR_LINKS:
        rest.pop()
    body = {"rgb": COLORS[words[-1]]}
    if " ".join(rest) in ALL_LIGHTS:
        return "color", "all", body
    target = [w for w in rest if w not in ARTICLES]
    if not target or len(target) > 3 or any(w.isdigit() for w in target):
        return None
    return "color", " ".join(target), body


def parse_fast_order(message):
    """'"Apaga todas las luces."' -> ("off", "all", None); '"pon los monitores en rojo"' ->
    ("color", "monitores", {"rgb": [255, 0, 0]})."""
    text = normalize(message).strip('"')
    words = [w for w in re.sub(r"[^\w ]", " ", text).split() if w not in FILLER]
    if len(words) < 2 or "?" in text:
        return None
    color = parse_color_order(words)
    if color:
        return color
    # Local Whisper mishears a letter ("apara" for "apaga"); accept a same-length near miss only,
    # so other conjugations ("apagaste") stay with the model.
    same_length = [v for v in FAST_VERBS if len(v) == len(words[0])]
    verb = difflib.get_close_matches(words[0], same_length, n=1, cutoff=0.8)
    if not verb:
        return None
    words[0] = verb[0]
    target = " ".join(words[1:])
    if target in ALL_LIGHTS:
        return FAST_VERBS[words[0]], "all", None
    target_words = [w for w in words[1:] if w not in ARTICLES]
    if not target_words or len(target_words) > 3 or any(w.isdigit() for w in target_words):
        return None
    return FAST_VERBS[words[0]], " ".join(target_words), None


MUSIC_WORDS = {"musica", "cancion", "alexa", "reproduccion"}
PLAY_VERBS = {"reproduce", "reproduceme", "reproducir", "toca", "tocame"}
# A play request made only of these words names nothing ("la música que quieras", "algo"): the model
# picks the artist (with the user's taste and exclusions from SOUL.md) instead of Alexa searching it.
VAGUE = {"la", "el", "los", "las", "un", "una", "unos", "unas", "musica", "cancion", "canciones", "algo", "lo",
         "que", "tu", "quieras", "quiera", "sea", "cualquier", "cualquiera", "cosa", "te", "guste", "gustes",
         "elijas", "escojas", "decidas", "de", "mi", "me", "sorprendeme", "bueno", "buena", "buenas", "otra", "otro",
         "a", "gusto", "tuyo", "tuya", "eleccion", "libre"}
LEVELS = ["cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez"]
VOLUME = re.compile(r"^(?:pon |sube |baja )?(?:el )?volumen (?:de alexa )?(?:a |al |en )?(\d{1,3}|"
                    + "|".join(LEVELS) + r")( ciento)?$")  # "%" and filler "por" are gone by then


CHOICE = {"quieras", "quiera", "elijas", "elige", "escojas", "escoge", "decidas", "sorprendeme", "gustes"}
GENERIC = {"musica", "algo", "cancion", "canciones", "una", "unas", "lo"}


def leaves_choice(query):
    """True when the user leaves the pick to Finnip: "lo que quieras para hacer el aseo",
    "música para concentrarme", "algo tranquilo". "música de los 80" or "algo de Queen" name it."""
    words = normalize(query).split()
    if set(words) <= VAGUE or CHOICE & set(words):
        return True
    return words[0] in GENERIC and (len(words) == 1 or words[1] != "de")


# The user's routines ("cuando diga X, responde Y y haz Z"), edited in the panel (/panel.html) and stored
# by the voice gateway. Read on every phrase, so a change applies at once.
ROUTINES_FILE = os.environ.get("FINNIP_ROUTINES", "/opt/finnip-routines/routines.json")
ROUTINE_MATCH = 0.85  # "Despier, ya llegó papá" still matches "despierta, ya llegó papá"


def load_routines():
    try:
        with open(ROUTINES_FILE) as f:
            routines = json.load(f).get("routines", [])
    except (OSError, ValueError, AttributeError):
        return []
    return [r for r in routines if isinstance(r, dict) and str(r.get("phrase") or "").strip()]


def _words(text):
    return re.sub(r"[^\w ]", " ", normalize(text)).split()


def routine(message, routines=None):
    """The routine whose phrase is said in the message (tolerant to how the STT spells it), or None."""
    words = _words(message)
    for item in load_routines() if routines is None else routines:
        phrase = " ".join(_words(item["phrase"]))
        n = len(phrase.split())
        for i in range(max(1, len(words) - n + 1)):
            if difflib.SequenceMatcher(None, " ".join(words[i:i + n]), phrase).ratio() >= ROUTINE_MATCH:
                return item
    return None


def run_routine(item):
    """Does the routine's mode, actions and music -> (its exact reply, what failed). The voice gateway
    calls it directly (no model at all); Hermes (Telegram) through routine_fast_path."""
    failed = []
    try:
        devices = call_bridge("GET", "/devices").get("devices", [])
        if item.get("mode"):
            scripts = {normalize(d.get("name", "")): d for d in devices if d.get("domain") == "script"}
            name = difflib.get_close_matches(normalize(item["mode"]), list(scripts), n=1, cutoff=0.8)
            if name:
                call_bridge("POST", f"/devices/{scripts[name[0]]['id']}/run")
            else:
                failed.append(f"no existe el modo {item['mode']}")
        for step in item.get("steps") or []:  # lights, colors, volume: Home Bridge checks each one
            try:
                call_bridge("POST", f"/devices/{step['device']}/{step['action']}", step.get("params") or None)
            except Exception as error:
                failed.append(f"{step.get('device')}: {error}")
        if item.get("music"):
            speakers = [d for d in devices if d.get("domain") == "media_player"]
            if speakers:
                call_bridge("POST", f"/devices/{speakers[0]['id']}/play", {"query": item["music"]})
            else:
                failed.append("no hay bocina")
    except Exception as error:
        failed.append(str(error))
    return str(item.get("reply") or "").strip() or "Listo, señor.", failed


def routine_fast_path(user_message):
    """Runs the routine before the model's turn; the model only says its reply."""
    item = routine(user_message)
    if item is None:
        return None
    reply, failed = run_routine(item)
    if not failed:
        return {"action": "block", "message": reply}  # said word for word: no model turn at all
    note =f" Después, en una frase corta, dile que falló: {'; '.join(failed)}." if failed else ""
    return {"context": (f"[finnip fast path] La rutina del usuario «{item['phrase']}» YA se ejecutó. Responde exactamente "
                        f"y solo esto, sin agregar nada ni llamar herramientas: «{reply}».{note}")}


def parse_music_order(message):
    """Short, unambiguous orders for the Alexa speaker -> (action, body), else None.
    '"Pausa la música."' -> ("pause", None); '"Reproduce Coldplay en Alexa"' -> ("play", {"query": "Coldplay"})."""
    raw = re.sub(r"^((oye|hey|ok) )?finnip[,.]?\s*", "", message.strip().strip('"').strip(), flags=re.IGNORECASE).rstrip(".!")
    text = normalize(raw)
    if "?" in text:
        return None
    words = [w for w in re.sub(r"[^\w ]", " ", text).split() if w not in FILLER]
    if not words or len(words) > 8:
        return None
    head, rest = words[0], set(words[1:])
    if head in {"pausa", "pausar", "pausala", "pausalo"} and len(words) <= 4:
        return "pause", None
    if head in {"deten", "detener", "para"} and rest & MUSIC_WORDS and len(words) <= 4:
        return "pause", None
    if len(words) <= 4 and (head in {"reanuda", "reanudar"} or
                            (head in {"continua", "continuar", "sigue", "seguir"} and rest & MUSIC_WORDS)):
        return "resume", None
    if len(words) == 1 and head in {"continua", "continuar", "sigue", "seguir", "continuala", "siguele"}:
        return "resume_if_paused", None  # "continúa" alone may mean "keep talking": only if music is paused
    volume = VOLUME.match(" ".join(words))
    if volume:
        n = LEVELS.index(volume.group(1)) if volume.group(1) in LEVELS else int(volume.group(1))
        if n <= 10 and not volume.group(2) and "%" not in raw:
            n *= 10  # "volumen a 3" is Alexa's 0-10 scale, not 3 %
        if n <= 100:
            return "volume", {"volume": n}
    if head in PLAY_VERBS and len(words) > 1:
        # Keep the user's own spelling for the search, minus the verb and a trailing "en Alexa".
        query = re.sub(r"\s+en (la )?alexa$", "", raw.split(None, 1)[1], flags=re.IGNORECASE)
        query = " ".join(re.sub(r"[.,;:!¡¿?]+", " ", query).split())  # "Iron Man. De Black Sabbath" from speech
        if not query or leaves_choice(query):
            return None
        return "play", {"query": query}
    return None


# "Modo estudio", "activa el modo cine", "voy a ver una película": runs the Home Assistant script named
# "Modo <x>" (lights and volume, edited in HA); then the model picks the music for it.
MODE = re.compile(r"^(?:(?:activa|activame|pon|ponme|entra|entremos|cambia|cambiame|inicia|arranca)(?: a| en| al)? )?"
                  r"(?:el )?mod(?:o|io) (\w+(?: \w+){0,2})$")  # "Modio": how the STT once wrote it
MOVIE = re.compile(r"^(?:voy|vamos) a ver (?:una )?(?:pelicula|peli)$")


def parse_mode_order(message):
    """'"Activa el modo trabajo profundo."' -> "modo trabajo profundo"; anything else -> None."""
    text = normalize(re.sub(r"^((oye|hey|ok) )?finnip[,.]?\s*", "", message.strip().strip('"'), flags=re.IGNORECASE))
    if "?" in text:
        return None
    text = " ".join(w for w in re.sub(r"[^\w ]", " ", text).split() if w not in FILLER)
    if MOVIE.match(text):
        return "modo cine"
    mode = MODE.match(text)
    return f"modo {mode.group(1)}" if mode else None


def mode_fast_path(user_message):
    mode = parse_mode_order(user_message)
    if mode is None:
        return None
    try:
        scripts = {normalize(d.get("name", "")): d for d in call_bridge("GET", "/devices").get("devices", [])
                   if d.get("domain") == "script"}
        name = difflib.get_close_matches(mode, list(scripts), n=1, cutoff=0.8)  # "modo calido" for "cálido"
        if not name:
            existing = ", ".join(d.get("name", d["id"]) for d in scripts.values()) or "ninguno"
            return {"context": (
                f"[finnip fast path] El usuario pidió el {mode}, pero no existe en Home Assistant (no lo intentes "
                f"activar). Modos que existen ahora: {existing}. Díselo en una frase y ofrécele crearlo con "
                "finnip_lights save_mode (por ejemplo con los valores actuales de sus luces).")}
        result = call_bridge("POST", f"/devices/{scripts[name[0]]['id']}/run")
    except Exception as error:
        return {"context": f"[finnip fast path] Intenté activar el {mode} antes de tu turno y falló: {error}. "
                           "Resuélvelo tú normalmente."}
    music = ("Este modo no lleva música: no reproduzcas nada." if scripts[name[0]].get("music") is False else
             f"Ahora elige tú un artista o canción concreto que vaya con el {name[0]} y reprodúcelo con "
             "finnip_lights play en la Echo (nunca reggaetón, banda ni cumbia).")
    return {"context": (
        f"[finnip fast path] El {name[0]} YA se activó antes de tu turno (luces y volumen): "
        f"{json.dumps(result, ensure_ascii=False)}. {music} Luego confirma al usuario en una frase corta.")}


def fast_targets(target, devices, action="on"):
    """Device ids for a parsed target: every light for "all", else the one device whose name
    contains every target word. None when nothing or more than one device matches."""
    if target == "all":
        ids = [d["id"] for d in devices if d.get("domain") == "light"
               and (action != "color" or "color" in d.get("capabilities", ["color"]))]
        return ids or None
    wanted = set(target.split())
    ids = [d["id"] for d in devices if wanted <= set(normalize(d.get("name", "")).split())]
    return ids if len(ids) == 1 else None


def music_fast_path(user_message):
    order = parse_music_order(user_message)
    if order is None:
        return None
    action, body = order
    try:
        speakers = [d for d in call_bridge("GET", "/devices").get("devices", []) if d.get("domain") == "media_player"]
        if len(speakers) != 1:
            return None
        if action == "resume_if_paused":
            if speakers[0].get("state") != "paused":
                return None
            action = "resume"
        result = call_bridge("POST", f"/devices/{speakers[0]['id']}/{action}", body)
    except Exception as error:
        return {"context": f"[finnip fast path] Intenté '{action}' en Alexa antes de tu turno y falló: {error}. "
                           "Resuélvelo tú normalmente."}
    if action != "play" and confirmed({action: result}):
        return {"action": "block", "message": DONE}
    # Alexa takes a few seconds to change songs: the title in the reply may still be the previous one.
    heard = (f"Pedí '{body['query']}'. NO digas qué canción suena (el título de la respuesta puede ser el de "
             "antes): confirma solo lo que pusiste. " if action == "play" else "")
    return {"context": (
        f"[finnip fast path] Esta orden de música YA se ejecutó en Alexa antes de tu turno: {action}. "
        f"Respuesta de Home Bridge: {json.dumps(result, ensure_ascii=False)}. {heard}"
        "No vuelvas a llamar herramientas ni a verificar; confirma al usuario en una frase corta.")}


# A confirmed order ends the turn with this reply (pre_llm_call "block"): no model call at all.
DONE = "Listo, señor."


def confirmed(results):
    return all(isinstance(r, dict) and r.get("confirmed") for r in results.values())


def run_order(action, ids, body):
    try:
        results = {id_: call_bridge("POST", f"/devices/{id_}/{action}", body) for id_ in ids}
    except Exception as error:
        return {"context": f"[finnip fast path] Intenté '{action}' antes de tu turno y falló: {error}. "
                           "Resuélvelo tú normalmente."}
    if confirmed(results):
        return {"action": "block", "message": DONE}
    return {"context": (
        f"[finnip fast path] Esta orden YA se ejecutó antes de tu turno: {action} en {', '.join(ids)}. "
        f"Respuesta de Home Bridge: {json.dumps(results, ensure_ascii=False)}. "
        "No vuelvas a llamar finnip_lights por esta orden; solo confirma brevemente al usuario.")}


# Jev (typesafe/jev-1.13 on OpenRouter, ~0.5 s) reads the short orders the regexes above miss
# ("deja a oscuras la lámpara", "quiero las luces rojas"), so the model of the moment is not the one
# deciding. Jev only picks among options built from the real devices and modes; below
# JEV_MIN_CONFIDENCE, on any error or without OPENROUTER_API_KEY, the message goes to the model.
JEV_URL = os.environ.get("JEV_URL", "https://openrouter.ai/api/alpha/decisions")
JEV_MODEL = os.environ.get("JEV_MODEL", "typesafe/jev-1.13")
JEV_MIN_CONFIDENCE = float(os.environ.get("JEV_MIN_CONFIDENCE", "0.7"))
INTENTS = {
    "on": "Prender o encender un dispositivo o luz, ahora mismo",
    "off": "Apagar un dispositivo o luz, ahora mismo",
    "color": "Cambiar el color de una luz, ahora mismo",
    "mode": "Activar un modo o escena de la casa",
    "pause": "Pausar o detener la música",
    "resume": "Reanudar la música pausada",
    "other": "Cualquier otra cosa: preguntas, plática, poner música nueva, brillo, recordatorios, impresora, "
             "calendario, varias órdenes juntas",
}
COLOR_NAMES = ("rojo", "verde", "azul", "amarillo", "naranja", "morado", "lila", "rosa", "magenta", "cian",
               "turquesa", "blanco")
# Questions, negations, timers, conditions and chained orders stay with the model: acting on a misread
# one is worse than waiting for it.
NOT_FOR_JEV = {"que", "cual", "cuales", "cuanto", "cuanta", "cuantos", "cuantas", "como", "cuando", "donde",
               "quien", "porque", "esta", "estan", "hay", "puedes", "sabes", "no", "nunca", "y", "si", "luego",
               "despues", "manana", "minuto", "minutos", "hora", "horas", "segundos", "antes", "hasta"}


def jev_choices(message, questions):
    """{question: option} with Jev's pick, or None where it is not confident; {} on any failure."""
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key.startswith("sk-or-"):
        return {}
    body = {"model": JEV_MODEL, "state": {"message": message}, "questions": {
        qid: {"type": "choice", "instructions": text, "criteria": options}
        for qid, (text, options) in questions.items()}}
    request = urllib.request.Request(JEV_URL, data=json.dumps(body).encode("utf-8"), method="POST", headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=4) as response:
            answers = json.loads(response.read().decode("utf-8"))["answers"]
    except Exception:
        return {}
    picks = {}
    for qid, answer in answers.items():
        choice = (answer or {}).get("choice")
        sure = ((answer or {}).get("probabilities") or {}).get(choice, 0) >= JEV_MIN_CONFIDENCE
        picks[qid] = choice if sure else None
    return picks


def jev_fast_path(user_message):
    message = re.sub(r"^((oye|hey|ok) )?finnip[,.]?\s*", "", user_message.strip().strip('"'), flags=re.IGNORECASE)
    words = [w for w in _words(message) if w not in FILLER]
    if not 2 <= len(words) <= 12 or "?" in message or NOT_FOR_JEV & set(words) or any(w.isdigit() for w in words):
        return None
    try:
        devices = call_bridge("GET", "/devices").get("devices", [])
    except Exception:
        return None
    things = {f"d{i}": d for i, d in enumerate(devices) if d.get("domain") not in ("script", "media_player")}
    modes = {f"m{i}": d for i, d in enumerate(devices) if d.get("domain") == "script"}
    speakers = [d for d in devices if d.get("domain") == "media_player"]
    questions = {"intent": ("¿Qué orden directa da el usuario, si da una?", INTENTS),
                 "color": ("Si pide un color, ¿cuál?", {c: c for c in COLOR_NAMES})}
    if things:
        questions["target"] = ("¿Sobre qué dispositivo es la orden?", {
            "all": "Todas las luces", **{k: d.get("name") or d["id"] for k, d in things.items()}})
    if modes:
        questions["mode"] = ("¿Qué modo pide?", {k: d.get("name") or d["id"] for k, d in modes.items()})
    pick = jev_choices(message, questions)
    intent = pick.get("intent")
    if intent in ("on", "off", "color"):
        target = pick.get("target")
        ids = fast_targets("all", devices, intent) if target == "all" else [things[target]["id"]] if target in things else None
        if not ids or (intent == "color" and not pick.get("color")):
            return None
        return run_order(intent, ids, {"rgb": COLORS[pick["color"]]} if intent == "color" else None)
    if intent == "mode" and pick.get("mode") in modes:
        return mode_fast_path(modes[pick["mode"]].get("name") or "")  # its own parser reads "Modo cine"
    if intent in ("pause", "resume") and len(speakers) == 1:
        return run_order(intent, [speakers[0]["id"]], None)
    return None


def fast_path_hook(user_message=None, **kwargs):
    if not isinstance(user_message, str) or "\n" in user_message.strip():
        return None
    done = routine_fast_path(user_message)
    if done is not None:
        return done
    mode = mode_fast_path(user_message)
    if mode is not None:
        return mode
    order = parse_fast_order(user_message)
    if order is None:
        return music_fast_path(user_message) or jev_fast_path(user_message)
    action, target, body = order
    try:
        ids = fast_targets(target, call_bridge("GET", "/devices").get("devices", []), action)
    except Exception as error:
        return {"context": f"[finnip fast path] Intenté '{action}' antes de tu turno y falló: {error}. "
                           "Resuélvelo tú normalmente."}
    return run_order(action, ids, body) if ids else jev_fast_path(user_message)  # "apágame todo"


def register(ctx):
    ctx.register_tool(
        name="finnip_lights",
        toolset="finnip_lights",
        schema=SCHEMA,
        handler=handle,
    )
    ctx.register_hook("pre_llm_call", fast_path_hook)
