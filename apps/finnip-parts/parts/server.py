"""finnip-parts HTTP API, for Hermes (plugin) and the voice gateway only, inside the Compose network.

GET  /health                                  public
GET  /parts                                   list
GET  /parts/<slug>[?version=n]                part, versions, code and slice of one version
POST /parts/<slug>/versions                   {code, name?, description?, note?} -> new version
POST /parts/<slug>/versions/<n>/slice         {material?: PLA|PETG, settings?: {cura_key: value}}
GET  /parts/<slug>/v<n>.(stl|gcode|scad)      file
"""

import hmac
import json
import logging
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .cura import SettingsError
from .scad import RenderError
from .store import NotFound, Store

MAX_BODY = 256 * 1024
# ponytail: one render or slice at a time for the whole service (4 cores, 8 GB shared with everything
# else); per-part locks if two people ever design at once.
WORK = threading.Lock()
log = logging.getLogger("finnip-parts")


def make_handler(store, api_key):
    class Handler(BaseHTTPRequestHandler):
        server_version = "finnip-parts"

        def log_message(self, fmt, *args):
            log.info("%s %s", self.command, self.path.split("?")[0])

        def reply(self, status, body=None, content_type="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def authorized(self):
            given = self.headers.get("Authorization", "")
            return hmac.compare_digest(given.encode(), f"Bearer {api_key}".encode())

        def body(self):
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                raise RenderError("Cuerpo demasiado grande")
            data = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(data, dict):
                raise RenderError("Se esperaba un objeto JSON")
            return data

        def handle_route(self):
            url = urlparse(self.path)
            path = url.path.rstrip("/")
            if self.command == "GET" and path == "/health":
                return self.reply(200, {"status": "ok", "service": "finnip-parts"})
            if not self.authorized():
                return self.reply(401, {"error": "No autorizado"})
            if self.command == "GET" and path == "/parts":
                return self.reply(200, {"parts": store.list()})
            match = re.fullmatch(r"/parts/([^/]+)/v(\d+)\.(stl|gcode|scad)", path)
            if self.command == "GET" and match:
                file, kind = store.file(*match.groups())
                return self.reply(200, file.read_bytes(), kind)
            match = re.fullmatch(r"/parts/([^/]+)", path)
            if self.command == "GET" and match:
                version = parse_qs(url.query).get("version", [None])[0]
                return self.reply(200, store.get(match.group(1), int(version) if version else None))
            match = re.fullmatch(r"/parts/([^/]+)/versions", path)
            if self.command == "POST" and match:
                body = self.body()
                if not isinstance(body.get("code"), str) or not body["code"].strip():
                    raise RenderError("Falta el código OpenSCAD de la pieza")
                with WORK:
                    record = store.add_version(match.group(1), body["code"], body.get("name"),
                                               body.get("description"), body.get("note"))
                return self.reply(201, record)
            match = re.fullmatch(r"/parts/([^/]+)/versions/(\d+)/slice", path)
            if self.command == "POST" and match:
                body = self.body()
                settings = body.get("settings") or {}
                if not isinstance(settings, dict):
                    raise SettingsError("settings debe ser un objeto {ajuste: valor}")
                with WORK:
                    result = store.slice(match.group(1), int(match.group(2)), body.get("material") or "PLA", settings)
                return self.reply(200, result)
            return self.reply(404, {"error": "Ruta desconocida"})

        def dispatch(self):
            try:
                self.handle_route()
            except NotFound as error:
                self.reply(404, {"error": str(error)})
            except (RenderError, SettingsError, ValueError) as error:
                self.reply(400, {"error": str(error)})
            except Exception:
                log.exception("request failed")
                self.reply(500, {"error": "Error interno del servicio de piezas"})

        do_GET = do_POST = dispatch

    return Handler


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    api_key = os.environ.get("PARTS_API_KEY", "")
    if len(api_key) < 32:
        raise SystemExit("PARTS_API_KEY debe tener al menos 32 caracteres")
    store = Store(os.environ.get("PARTS_DIR", "/data/parts"))
    server = ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "3100"))), make_handler(store, api_key))
    log.info("finnip-parts escuchando en %s", server.server_address)
    server.serve_forever()


if __name__ == "__main__":
    main()
