"""Finnip designs 3D parts and prints them (finnip-parts service, OctoPrint).

The model writes each part as OpenSCAD code; the finnip-parts service renders it, keeps every version
and slices it with CuraEngine for the Ender-3 V3 SE. Printing uploads the G-code to OctoPrint, and the
finnip-printer watcher announces the end and powers the printer off as with any other print."""
import base64
import json
import os
import re
import unicodedata
import urllib.error
import urllib.request
import uuid

PARTS_URL = os.environ.get("PARTS_URL", "http://parts:3100").rstrip("/")
OCTOPRINT_URL = os.environ.get("OCTOPRINT_URL", "http://octoprint").rstrip("/")
GATEWAY_URL = os.environ.get("VOICE_GATEWAY_URL", "http://voice-gateway:8765").rstrip("/")
ACTIONS = ("design", "list", "get", "show", "slice", "print", "look")
LOOK_NOTE = (
    "Foto de la cámara de la Mac, tomada ahora porque el usuario lo pidió. Identifica el objeto. Si es un "
    "producto conocido, usa sus medidas oficiales y dilo. Si no, pide al usuario las medidas que importan para "
    "el ajuste; con una tarjeta de crédito (85.60 × 53.98 mm) en el mismo plano puedes estimar, pero di que es "
    "aproximado.")


def slugify(name):
    """'Soporte del cargador' -> 'soporte_del_cargador': the part's id in the service."""
    text = unicodedata.normalize("NFKD", str(name or "").casefold())
    text = "".join(c for c in text if not unicodedata.combining(c))
    slug = re.sub(r"[^a-z0-9]+", "_", text).strip("_")[:40]
    if not slug:
        raise ValueError("Falta el nombre de la pieza")
    return slug


def _request(url, method="GET", body=None, headers=None, timeout=30, raw=False):
    headers = dict(headers or {})
    data = None
    if isinstance(body, bytes):
        data = body
    elif body is not None:
        data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content = response.read()
    return content if raw else (json.loads(content) if content else {})


def parts(method, path, body=None, raw=False):
    key = os.environ.get("PARTS_API_KEY")
    if not key:
        raise RuntimeError("PARTS_API_KEY no está configurada")
    try:
        # Rendering and slicing wait for the service's single worker: generous timeout.
        return _request(PARTS_URL + path, method, body, {"Authorization": f"Bearer {key}"}, timeout=180, raw=raw)
    except urllib.error.HTTPError as error:
        try:
            detail = json.loads(error.read()).get("error")
        except (ValueError, AttributeError):
            detail = None
        raise RuntimeError(detail or f"El servicio de piezas devolvió HTTP {error.code}") from error
    except urllib.error.URLError as error:
        raise RuntimeError("No se pudo conectar con el servicio de piezas") from error


def octoprint(method, path, body=None, headers=None):
    headers = {"X-Api-Key": os.environ.get("OCTOPRINT_API_KEY", ""), **(headers or {})}
    return _request(OCTOPRINT_URL + path, method, body, headers, timeout=60)


def printer_problem():
    """Why the printer cannot start a print now, or None when it can."""
    try:
        printer = octoprint("GET", "/api/printer?exclude=sd,temperature")
    except urllib.error.HTTPError as error:
        if error.code == 409:
            return "La impresora no está conectada a OctoPrint (seguramente apagada): enciéndela con finnip_printer power_on"
        raise
    flags = printer.get("state", {}).get("flags", {})
    if flags.get("printing") or flags.get("paused") or flags.get("pausing") or flags.get("cancelling"):
        return "La impresora ya está ocupada con otra impresión"
    if not flags.get("operational") or flags.get("error"):
        return f"La impresora no está lista: {printer.get('state', {}).get('text', 'estado desconocido')}"
    return None


def upload_and_print(filename, gcode):
    boundary = uuid.uuid4().hex
    parts_ = [
        (f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
         "Content-Type: application/octet-stream\r\n\r\n").encode() + gcode,
        b'Content-Disposition: form-data; name="select"\r\n\r\ntrue',
        b'Content-Disposition: form-data; name="print"\r\n\r\ntrue',
    ]
    body = b"".join(f"--{boundary}\r\n".encode() + p + b"\r\n" for p in parts_) + f"--{boundary}--\r\n".encode()
    return octoprint("POST", "/api/files/local", body, {"Content-Type": f"multipart/form-data; boundary={boundary}"})


def look():
    """One frame from the desktop app's camera, as an image the model sees (Hermes multimodal result)."""
    key = os.environ.get("PARTS_API_KEY", "")
    try:
        jpeg = _request(GATEWAY_URL + "/internal/photo", "POST", b"", {"Authorization": f"Bearer {key}"},
                        timeout=25, raw=True)
    except urllib.error.HTTPError as error:
        if error.code == 409:
            raise RuntimeError("La app de escritorio no está abierta: no hay cámara para tomar la foto") from error
        if error.code == 504:
            raise RuntimeError("La app de escritorio no mandó la foto a tiempo") from error
        try:
            detail = json.loads(error.read()).get("error")
        except (ValueError, AttributeError):
            detail = None
        raise RuntimeError(detail or "No pude tomar la foto") from error
    except urllib.error.URLError as error:
        raise RuntimeError("No pude contactar al voice gateway para tomar la foto") from error
    return {
        "_multimodal": True,
        "content": [{"type": "text", "text": LOOK_NOTE},
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()}}],
        "text_summary": f"Foto de la cámara ({len(jpeg) // 1024} KB) adjunta para el modelo principal.",
    }


def _version(params):
    version = params.get("version")
    return f"?version={int(version)}" if version else ""


def run(params):
    action = params.get("action")
    if action not in ACTIONS:
        raise ValueError("Acción no permitida")
    if action == "list":
        return parts("GET", "/parts")
    if action == "look":
        return look()
    slug = slugify(params.get("name"))
    if action == "design":
        code = params.get("code")
        if not isinstance(code, str) or not code.strip():
            raise ValueError("Falta el código OpenSCAD de la pieza")
        body = {"code": code, "name": params.get("name"), "description": params.get("description"),
                "note": params.get("note")}
        return {"slug": slug, **parts("POST", f"/parts/{slug}/versions", body)}
    part = parts("GET", f"/parts/{slug}{_version(params)}")
    current = part["current"]
    if action == "get":
        return part
    if action == "show":
        key = os.environ.get("PARTS_API_KEY", "")
        try:
            _request(GATEWAY_URL + "/internal/part", "POST",
                     {"slug": slug, "version": current["version"], "name": part["name"], "size_mm": current["size_mm"]},
                     {"Authorization": f"Bearer {key}"}, timeout=10)
        except urllib.error.HTTPError as error:
            if error.code == 409:  # the gateway has no desktop app connected
                raise RuntimeError("La app de escritorio no está abierta: no hay holograma donde mostrarla") from error
            raise RuntimeError("El holograma de piezas todavía no está disponible") from error
        except urllib.error.URLError as error:
            raise RuntimeError("No pude contactar al voice gateway para mostrar la pieza") from error
        return {"shown": slug, "version": current["version"]}
    if action == "slice":
        body = {"material": params.get("material") or "PLA", "settings": params.get("settings") or {}}
        return parts("POST", f"/parts/{slug}/versions/{current['version']}/slice", body)
    # print
    sliced = current.get("slice")
    if not sliced:
        raise ValueError(f"La versión {current['version']} de {part['name']} no está rebanada: usa slice primero")
    if params.get("confirmed") is not True:
        raise ValueError("Falta la confirmación del usuario (confirmed: true) de que la cama está libre")
    problem = printer_problem()
    if problem:
        raise RuntimeError(problem)
    gcode = parts("GET", f"/parts/{slug}/v{current['version']}.gcode", raw=True)
    upload_and_print(f"{slug}_v{current['version']}_{sliced['material'].lower()}.gcode", gcode)
    return {"printing": part["name"], "version": current["version"], "material": sliced["material"],
            "seconds": sliced["seconds"], "grams": sliced["grams"]}


SCHEMA = {
    "name": "finnip_parts",
    "description": (
        "Diseña piezas 3D y las imprime en la Ender-3 V3 SE. "
        "design crea una pieza o una versión nueva: escribe la pieza completa en OpenSCAD en code (en mm; sin "
        "import, include, use ni surface) y responde con size_mm y avisos; si OpenSCAD falla, corrige el código. "
        "Para cambiar una pieza, lee su código con get, modifícalo y guárdalo con design y el mismo name (las "
        "versiones anteriores se conservan). list lista las piezas; show la muestra en el holograma del escritorio. "
        "slice la rebana con Cura para PLA (por defecto) o PETG y ajustes opcionales de Cura en settings "
        "(por ejemplo {\"infill_sparse_density\": 40, \"support_enable\": true}); devuelve tiempo en segundos, "
        "gramos y avisos. print imprime la última versión rebanada: ANTES di nombre, material, tiempo y gramos, "
        "pregunta si la cama está libre y espera un sí explícito; solo entonces llama print con confirmed true. "
        "look toma una foto con la cámara de la Mac (solo cuando el usuario pide que mires o midas algo) y te la "
        "muestra, para identificar el objeto y sus medidas."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": list(ACTIONS)},
            "name": {"type": "string", "maxLength": 60, "description": "Nombre de la pieza, por ejemplo 'soporte del cargador'"},
            "code": {"type": "string", "maxLength": 100000, "description": "Para design: código OpenSCAD completo de la pieza"},
            "description": {"type": "string", "maxLength": 300, "description": "Para design: para qué es la pieza"},
            "note": {"type": "string", "maxLength": 200, "description": "Para design: qué cambió en esta versión"},
            "version": {"type": "integer", "minimum": 1, "description": "Versión; por defecto la última"},
            "material": {"type": "string", "enum": ["PLA", "PETG"], "description": "Para slice; PLA si el usuario no dice"},
            "settings": {"type": "object", "description": "Para slice: ajustes de Cura que pidió el usuario para esta pieza"},
            "confirmed": {"type": "boolean", "description": "Para print: true solo si el usuario confirmó que la cama está libre"},
        },
        "required": ["action"],
        "additionalProperties": False,
    },
}


def handle(params, **kwargs):
    try:
        result = run(params)
        if isinstance(result, dict) and result.get("_multimodal"):
            return result  # the photo goes to the model as an image
        return json.dumps({"success": True, "action": params.get("action"), "result": result}, ensure_ascii=False)
    except Exception as error:
        return json.dumps({"success": False, "error": str(error)}, ensure_ascii=False)


def register(ctx):
    ctx.register_tool(name="finnip_parts", toolset="finnip_parts", schema=SCHEMA, handler=handle)
