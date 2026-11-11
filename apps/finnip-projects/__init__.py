"""Finnip programs by voice: projects in ~/Projects on the user's Mac, worked on by Claude Code.

Every action goes to the voice gateway, which asks the desktop app on the Mac (projects.rs there checks
names, repositories and commands). A Claude Code task answers "started" at once; when it finishes, the
gateway puts the result in the voice conversation so Finnip tells the user."""
import json
import os
import re
import unicodedata
import urllib.error
import urllib.request

GATEWAY_URL = os.environ.get("VOICE_GATEWAY_URL", "http://voice-gateway:8765").rstrip("/")
ACTIONS = ("list", "create", "open", "task", "run", "stop", "find", "delete")
TIMEOUT = 170  # s: a clone or a dev server's first build (the gateway gives up at 150)


def slugify(name):
    """'Mi Tienda' -> 'mi-tienda': the project's folder in ~/Projects."""
    text = unicodedata.normalize("NFKD", str(name or "").casefold())
    text = "".join(c for c in text if not unicodedata.combining(c))
    slug = re.sub(r"[^a-z0-9_]+", "-", text).strip("-_")[:60]
    if not slug:
        raise ValueError("Falta el nombre del proyecto")
    return slug


def call_gateway(body):
    key = os.environ.get("PARTS_API_KEY", "")
    request = urllib.request.Request(GATEWAY_URL + "/internal/project", data=json.dumps(body).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        try:
            detail = json.loads(error.read()).get("error")
        except (ValueError, AttributeError):
            detail = None
        raise RuntimeError(detail or f"El voice gateway devolvió HTTP {error.code}") from error
    except urllib.error.URLError as error:
        raise RuntimeError("No pude contactar al voice gateway") from error


def run(params):
    action = params.get("action")
    if action not in ACTIONS:
        raise ValueError("Acción no permitida")
    body = {"action": action, "where": "cloud" if params.get("where") == "cloud" else "local"}
    path = str(params.get("path") or "").strip()
    if path and body["where"] == "local" and action in ("open", "task", "run", "stop"):
        body["path"] = path[:300]  # a folder in ~/Documents (or ~/Projects), relative to home
    elif action == "find":
        body["name"] = str(params.get("name") or "").strip()[:60]  # the folder's name as the user says it
        if not body["name"]:
            raise ValueError("Falta el nombre de la carpeta a buscar")
    elif action != "list":
        body["name"] = slugify(params.get("name"))
    if action == "delete":
        body["confirmed"] = params.get("confirmed") is True
    if action == "create" and params.get("repo"):
        body["repo"] = str(params["repo"]).strip()[:200]
    if action == "task":
        request = str(params.get("request") or "").strip()
        if not request:
            raise ValueError("Falta request: lo que el usuario quiere en el proyecto, con sus palabras")
        body["request"] = request[:4000]
        body["confirmed"] = params.get("confirmed") is True
    return call_gateway(body)


SCHEMA = {
    "name": "finnip_projects",
    "description": (
        "Proyectos de software del usuario, programados por Claude Code: en su Mac (~/Projects, where 'local', por "
        "defecto) o en el servidor (/srv/projects, where 'cloud', cuando dice 'en la nube'). "
        "list: proyectos que hay. create: proyecto nuevo con name, o retomar un repositorio de GitHub con name y "
        "repo ('dueño/nombre'); se abre en Zed. open: abrirlo en Zed. task: pedirle a Claude Code un cambio en el "
        "proyecto; en request van las palabras del usuario completas y el contexto que sepas. Responde 'started': "
        "dile al usuario que ya está en eso y que le avisas al terminar (el resultado te llega solo; no esperes ni "
        "vuelvas a llamar). Claude Code trabaja solo pero se detiene antes de algo importante (push, borrar, "
        "publicar, pagar): entonces pregúntale al usuario y SOLO con un sí explícito llama task con confirmed true y "
        "request 'Confirmado: ...'. run: correr el proyecto; en la Mac abre el navegador, en la nube queda en "
        "http://<proyecto>.dev.finnip, varios a la vez (devuelve url). stop: detenerlo. Usa el mismo where en todas las acciones de un proyecto. "
        "Carpetas de la Mac fuera de ~/Projects (solo dentro de ~/Documents): open, task, run y stop con path relativo "
        "al home, por ejemplo 'Documents/clientes/tienda'; si no sabes la ruta exacta, find con name busca carpetas "
        "por nombre y devuelve sus paths. delete manda un proyecto de ~/Projects o de la nube a la papelera: ANTES "
        "pregunta solo '¿Elimino <nombre>?' y SOLO con un sí llama con confirmed true."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": list(ACTIONS)},
            "name": {"type": "string", "maxLength": 60, "description": "Nombre del proyecto, por ejemplo 'tienda'"},
            "repo": {"type": "string", "maxLength": 200, "description": "Para create: repositorio de GitHub a retomar, 'dueño/nombre'"},
            "request": {"type": "string", "maxLength": 4000, "description": "Para task: lo que hay que hacer, con las palabras del usuario"},
            "confirmed": {"type": "boolean", "description": "Para task o delete: true solo si el usuario dijo que sí explícitamente"},
            "where": {"type": "string", "enum": ["local", "cloud"], "description": "local por defecto"},
            "path": {"type": "string", "maxLength": 300,
                     "description": "Carpeta de la Mac relativa al home, dentro de Documents, por ejemplo 'Documents/clientes/tienda'"},
        },
        "required": ["action"],
        "additionalProperties": False,
    },
}


def handle(params, **kwargs):
    try:
        return json.dumps({"success": True, "action": params.get("action"), "result": run(params)}, ensure_ascii=False)
    except Exception as error:
        return json.dumps({"success": False, "error": str(error)}, ensure_ascii=False)


def register(ctx):
    ctx.register_tool(name="finnip_projects", toolset="finnip_projects", schema=SCHEMA, handler=handle)
