import difflib
import json
import os
import re
import unicodedata
import urllib.error
import urllib.request

BRIDGE_URL = os.environ.get("FINNIP_BRIDGE_URL", "http://home-bridge:3000").rstrip("/")

ACTIONS = (
    "list", "status", "on", "off", "brightness", "color",
    "open", "close", "stop", "position", "temperature", "hvac_mode",
)
# Parameters each action forwards to Home Bridge, which validates them again.
ACTION_FIELDS = {
    "brightness": ("brightness",),
    "color": ("rgb", "brightness"),
    "position": ("position",),
    "temperature": ("temperature",),
    "hvac_mode": ("hvac_mode",),
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


def resolve_device(device):
    """Accept an entity_id or a device name, so the model can act without a prior list call."""
    if ENTITY_ID.match(device):
        return device
    query = normalize(device)
    devices = call_bridge("GET", "/devices").get("devices", [])
    names = {d["id"]: normalize(d.get("name", "")) for d in devices}
    exact = [id_ for id_, name in names.items() if name == query]
    partial = [id_ for id_, name in names.items() if name and (query in name or name in query)]
    matches = exact or partial
    if len(matches) == 1:
        return matches[0]
    available = ", ".join(d.get("name", d["id"]) for d in devices) or "ninguno"
    problem = "es ambiguo" if matches else "no coincide con ningún dispositivo"
    raise ValueError(f"'{device}' {problem}. Disponibles: {available}")


def run(params):
    action = params.get("action")
    if action not in ACTIONS:
        raise ValueError("Acción no permitida")
    if action == "list":
        return call_bridge("GET", "/devices")

    device = params.get("device")
    if not isinstance(device, str) or not device.strip():
        raise ValueError("Falta el dispositivo: usa su nombre o su id")
    device = resolve_device(device)
    if action == "status":
        return call_bridge("GET", f"/devices/{device}")

    body = {field: params[field] for field in ACTION_FIELDS.get(action, ()) if field in params}
    return call_bridge("POST", f"/devices/{device}/{action}", body or None)


SCHEMA = {
    "name": "finnip_lights",
    "description": (
        "Controla los dispositivos del hogar que el usuario expuso a Finnip "
        "(luces, interruptores, persianas y climatización). "
        "Para actuar pasa directamente el nombre del dispositivo en device (por ejemplo 'lámpara'); "
        "no necesitas llamar list antes. Usa list solo para descubrir dispositivos o sus capabilities. "
        "Si el nombre no coincide o es ambiguo, el error incluye los dispositivos disponibles. "
        "Cada orden devuelve confirmed y actual con el estado que reporta Home Assistant."
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
        },
        "required": ["action"],
        "additionalProperties": False,
    },
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
ALL_LIGHTS = {"luces", "las luces", "todas las luces"}
FILLER = {"finnip", "por", "favor", "porfa", "porfavor"}
ARTICLES = {"el", "la", "los", "las", "de", "del"}


def parse_fast_order(message):
    """'"Apaga todas las luces."' -> ("off", "all"); '"prende la lámpara"' -> ("on", "lampara")."""
    text = normalize(message).strip('"')
    words = [w for w in re.sub(r"[^\w ]", " ", text).split() if w not in FILLER]
    if len(words) < 2 or "?" in text:
        return None
    # Local Whisper mishears a letter ("apara" for "apaga"); accept a same-length near miss only,
    # so other conjugations ("apagaste") stay with the model.
    same_length = [v for v in FAST_VERBS if len(v) == len(words[0])]
    verb = difflib.get_close_matches(words[0], same_length, n=1, cutoff=0.8)
    if not verb:
        return None
    words[0] = verb[0]
    target = " ".join(words[1:])
    if target in ALL_LIGHTS:
        return FAST_VERBS[words[0]], "all"
    target_words = [w for w in words[1:] if w not in ARTICLES]
    if not target_words or len(target_words) > 3 or any(w.isdigit() for w in target_words):
        return None
    return FAST_VERBS[words[0]], " ".join(target_words)


def fast_targets(target, devices):
    """Device ids for a parsed target: every light for "all", else the one device whose name
    contains every target word. None when nothing or more than one device matches."""
    if target == "all":
        ids = [d["id"] for d in devices if d.get("domain") == "light"]
        return ids or None
    wanted = set(target.split())
    ids = [d["id"] for d in devices if wanted <= set(normalize(d.get("name", "")).split())]
    return ids if len(ids) == 1 else None


def fast_path_hook(user_message=None, **kwargs):
    if not isinstance(user_message, str) or "\n" in user_message.strip():
        return None
    order = parse_fast_order(user_message)
    if order is None:
        return None
    action, target = order
    try:
        ids = fast_targets(target, call_bridge("GET", "/devices").get("devices", []))
        if not ids:
            return None
        results = {id_: call_bridge("POST", f"/devices/{id_}/{action}") for id_ in ids}
    except Exception as error:
        return {"context": f"[finnip fast path] Intenté '{action}' antes de tu turno y falló: {error}. "
                           "Resuélvelo tú normalmente."}
    return {"context": (
        f"[finnip fast path] Esta orden YA se ejecutó antes de tu turno: {action} en {', '.join(ids)}. "
        f"Respuesta de Home Bridge: {json.dumps(results, ensure_ascii=False)}. "
        "No vuelvas a llamar finnip_lights por esta orden; solo confirma brevemente al usuario.")}


def register(ctx):
    ctx.register_tool(
        name="finnip_lights",
        toolset="finnip_lights",
        schema=SCHEMA,
        handler=handle,
    )
    ctx.register_hook("pre_llm_call", fast_path_hook)
