import json
import os
import urllib.error
import urllib.request

BRIDGE_URL = os.environ.get("FINNIP_BRIDGE_URL", "http://home-bridge:3000").rstrip("/")


def call_bridge(action, rgb=None, brightness=None):
    api_key = os.environ.get("BRIDGE_API_KEY")

    if not api_key:
        raise RuntimeError("BRIDGE_API_KEY no está configurada")

    endpoints = {
        "status": ("GET", "/lights/monitores"),
        "on": ("POST", "/lights/monitores/on"),
        "off": ("POST", "/lights/monitores/off"),
        "color": ("POST", "/lights/monitores/color"),
    }

    method, path = endpoints[action]

    payload = None

    if action == "color":
        payload = json.dumps(
            {
                "rgb": rgb,
                "brightness": brightness if brightness is not None else 100,
            }
        ).encode("utf-8")

    request = urllib.request.Request(
        url=f"{BRIDGE_URL}{path}",
        data=payload,
        method=method,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    except urllib.error.HTTPError as error:
        raise RuntimeError(f"Home Bridge devolvió HTTP {error.code}") from error

    except urllib.error.URLError as error:
        raise RuntimeError("No se pudo conectar con Home Bridge") from error


def register(ctx):
    schema = {
        "name": "finnip_lights",
        "description": (
            "Controla las luces LED de los monitores de Finnip. "
            "Permite consultar su estado, encenderlas, apagarlas "
            "o cambiar su color RGB y brillo."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["status", "on", "off", "color"],
                    "description": "Operación a realizar",
                },
                "rgb": {
                    "type": "array",
                    "items": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 255,
                    },
                    "minItems": 3,
                    "maxItems": 3,
                    "description": "Color RGB, por ejemplo [128, 0, 255]",
                },
                "brightness": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "description": "Brillo del 1 al 100 por ciento",
                },
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    }

    def handle_lights(params, **kwargs):
        try:
            action = params.get("action")

            if action not in ("status", "on", "off", "color"):
                raise ValueError("Acción no permitida")

            if action == "color":
                rgb = params.get("rgb")

                if (
                    not isinstance(rgb, list)
                    or len(rgb) != 3
                    or any(
                        type(value) is not int or not 0 <= value <= 255 for value in rgb
                    )
                ):
                    raise ValueError("Color RGB inválido")

                brightness = params.get("brightness", 100)

                if type(brightness) is not int or not 1 <= brightness <= 100:
                    raise ValueError("Brillo inválido")

                result = call_bridge(
                    action,
                    rgb=rgb,
                    brightness=brightness,
                )
            else:
                result = call_bridge(action)

            return json.dumps(
                {
                    "success": True,
                    "action": action,
                    "result": result,
                },
                ensure_ascii=False,
            )

        except Exception as error:
            return json.dumps(
                {
                    "success": False,
                    "error": str(error),
                },
                ensure_ascii=False,
            )

    ctx.register_tool(
        name="finnip_lights",
        toolset="finnip_lights",
        schema=schema,
        handler=handle_lights,
    )
