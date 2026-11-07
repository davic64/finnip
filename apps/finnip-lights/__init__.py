import json
import os
import re
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


def run(params):
    action = params.get("action")
    if action not in ACTIONS:
        raise ValueError("Acción no permitida")
    if action == "list":
        return call_bridge("GET", "/devices")

    device = params.get("device")
    if not isinstance(device, str) or not ENTITY_ID.match(device):
        raise ValueError("Dispositivo inválido: usa un id devuelto por la acción list")
    if action == "status":
        return call_bridge("GET", f"/devices/{device}")

    body = {field: params[field] for field in ACTION_FIELDS.get(action, ()) if field in params}
    return call_bridge("POST", f"/devices/{device}/{action}", body or None)


SCHEMA = {
    "name": "finnip_lights",
    "description": (
        "Controla los dispositivos del hogar que el usuario expuso a Finnip "
        "(luces, interruptores, persianas y climatización). "
        "Usa action=list para descubrir los dispositivos, su id y sus capabilities. "
        "Solo ejecuta acciones incluidas en las capabilities del dispositivo. "
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
                "description": "id del dispositivo devuelto por list, por ejemplo light.leds_monitores",
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


def register(ctx):
    ctx.register_tool(
        name="finnip_lights",
        toolset="finnip_lights",
        schema=SCHEMA,
        handler=handle,
    )
