"""Finnip's projects in the cloud: the server's side of "Finnip, en la nube, nuevo proyecto…".

The same fixed actions as the Mac app (apps/finnip-desktop/src-tauri/src/projects.rs) on folders under
/srv/projects, served on a Unix socket in a folder only the voice gateway can enter (group 10000). Claude Code runs as
the user who logged in to it. Nothing here runs a command the caller wrote: names and repositories are
checked, and programs get their arguments without a shell interpreting them. A finished task is posted
to the gateway's /internal/project_done, which has Finnip tell the user."""
import json
import os
import re
import shutil
import signal
import socket
import socketserver
import subprocess
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path(os.environ.get("PROJECTS_ROOT", "/srv/projects"))
SOCKET = os.environ.get("RUNNER_SOCKET", "/srv/finnip/data/runner/runner.sock")
GATEWAY = os.environ.get("GATEWAY_URL", "http://127.0.0.1:8765").rstrip("/")
# Each running project gets a free port and its own name on the tailnet, http://<name>.dev.finnip: the
# route is added to Caddy at run time through its admin API (localhost only) and removed on stop.
PREVIEW_PORTS = range(4101, 4200)
CADDY_ADMIN = os.environ.get("CADDY_ADMIN", "http://127.0.0.1:2019")
URL_WAIT = 90
MAX_REQUEST = 4000
# Same policy as the Mac: bypass mode, it stops before anything important and Finnip asks the user.
SYSTEM = ("Te habla Finnip, el asistente de voz del usuario, con sus órdenes. Trabajas sin pedir permiso para "
          "editar, instalar dependencias del proyecto o correr comandos. Pero ANTES de algo importante o irreversible "
          "(borrar archivos o datos que no creaste en esta tarea, git push o reescribir historial, publicar o "
          "desplegar, gastar dinero o usar servicios de pago, tocar credenciales o secretos, instalar herramientas "
          "globales del sistema) NO lo hagas: termina con una línea que empiece con 'CONFIRMAR:' diciendo qué harías "
          "y por qué. Si la orden empieza con 'Confirmado:', el usuario ya lo autorizó: hazlo. Al terminar, responde "
          "en español con un resumen breve (2 o 3 frases, sin código ni rutas largas) de lo que hiciste y de lo que "
          "falte. Este proyecto corre en un servidor Linux; Finnip levanta su vista previa con --port, no fijes puertos.")
NEEDS_CONFIRMATION = ["Bash(git push:*)", "Bash(git reset --hard:*)", "Bash(sudo:*)", "Bash(npm publish:*)"]
NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,59}$")
REPO_PART = re.compile(r"^[A-Za-z0-9_.-]+$")
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


class Refused(Exception):
    pass


def valid_repo(repo):
    """'owner/name' or a github.com URL -> 'owner/name', else None."""
    repo = str(repo or "").strip().removeprefix("https://github.com/").rstrip("/").removesuffix(".git")
    parts = repo.split("/")
    ok = len(parts) == 2 and all(REPO_PART.match(p) and not p.startswith(".") for p in parts)
    return repo if ok else None


def program(name, *args):
    """argv for a program through the user's login shell (its PATH: fnm, ~/.local/bin); "$@" never parsed."""
    return ["/bin/bash", "-lc", 'exec "$0" "$@"', name, *args]


def read_result(stdout):
    """Claude Code's JSON -> (its last message, what needs the user's yes, error)."""
    try:
        value = json.loads(stdout)
    except ValueError:
        return stdout[:500], [], True
    result = value.get("result") or ""
    pending = [line.strip().lstrip("*- ").removeprefix("CONFIRMAR:").strip()
               for line in result.splitlines() if line.strip().lstrip("*- ").startswith("CONFIRMAR:")]
    for denial in value.get("permission_denials") or []:
        command = (denial.get("tool_input") or {}).get("command")
        pending.append(f"correr {command}" if command else denial.get("tool_name", "?"))
    return result, pending, bool(value.get("is_error"))


def find_url(line):
    match = re.search(r"http://(localhost|127\.0\.0\.1):\d+\S*", ANSI.sub("", line))
    return match.group(0).rstrip(".,)") if match else None


class Projects:
    def __init__(self, root=ROOT, notify=None, caddy=None):
        self.root = Path(root)
        self.sessions_file = self.root / ".finnip-sessions.json"
        self.notify = notify or post_done
        self.caddy = caddy or caddy_route
        self.busy, self.lock = set(), threading.Lock()
        self.previews = {}  # name -> (Popen, port) of each dev server behind <name>.dev.finnip

    def alive(self, name):
        preview = self.previews.get(name)
        return preview if preview and preview[0].poll() is None else None

    def path(self, name, exists=True):
        if not isinstance(name, str) or not NAME.match(name):
            raise Refused("Nombre de proyecto inválido: minúsculas, números, - y _")
        path = self.root / name
        if exists and not path.is_dir():
            raise Refused(f"No existe el proyecto {name} en la nube")
        return path

    def sessions(self):
        try:
            return json.loads(self.sessions_file.read_text())
        except (OSError, ValueError):
            return {}

    def handle(self, req):
        self.root.mkdir(parents=True, exist_ok=True)
        action = req.get("action")
        if action == "list":
            return self.list()
        if action == "create":
            return self.create(req.get("name"), req.get("repo"))
        if action == "open":
            return {"path": str(self.path(req.get("name")))}
        if action == "task":
            return self.task(req.get("name"), req.get("request"), bool(req.get("confirmed")))
        if action == "run":
            return self.run(req.get("name"))
        if action == "stop":
            return self.stop(req.get("name"))
        if action == "delete":
            return self.delete(req.get("name"), bool(req.get("confirmed")))
        raise Refused(f"Acción desconocida: {action}")

    def list(self):
        names = sorted(p.name for p in self.root.iterdir() if p.is_dir() and not p.name.startswith("."))
        return {"root": str(self.root), "projects": [
            {"name": n, "git": (self.root / n / ".git").exists(), "working": n in self.busy,
             "running": preview_url(n) if self.alive(n) else None} for n in names]}

    def create(self, name, repo=None):
        path = self.path(name, exists=False)
        if path.exists():
            raise Refused(f"Ya existe el proyecto {name} en la nube")
        if repo:
            repo = valid_repo(repo)
            if not repo:
                raise Refused("Repositorio inválido: usa dueño/nombre o su URL de GitHub")
            # ponytail: https clone, so only public repos (no GitHub login on the server); add gh auth for private.
            argv = program("git", "clone", "-q", f"https://github.com/{repo}.git", str(path))
        else:
            path.mkdir()
            argv = program("git", "init", "-q", str(path))
        out = subprocess.run(argv, capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL)
        if out.returncode != 0:
            if not repo:
                shutil.rmtree(path, ignore_errors=True)
            raise Refused((out.stderr or "git falló").strip()[:300])
        return {"created": name, "path": str(path), "cloned": bool(repo)}

    def task(self, name, request, confirmed=False):
        path = self.path(name)
        request = str(request or "").strip()
        if not request or len(request) > MAX_REQUEST:
            raise Refused("Falta lo que hay que hacer en el proyecto")
        with self.lock:
            if name in self.busy:
                raise Refused(f"Claude Code ya está trabajando en {name}")
            self.busy.add(name)
        threading.Thread(target=self._task, args=(name, path, request, confirmed), daemon=True).start()
        return {"started": name, "where": "cloud"}

    def _claude(self, path, request, confirmed, session):
        args = ["-p", request, "--output-format", "json", "--permission-mode", "bypassPermissions",
                "--setting-sources", "project", "--append-system-prompt", SYSTEM]
        if session:
            args += ["--resume", session]
        if not confirmed:
            args += ["--disallowedTools", *NEEDS_CONFIRMATION]
        return subprocess.run(program("claude", *args), cwd=path, capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, timeout=3600)

    def _task(self, name, path, request, confirmed):
        try:
            session = self.sessions().get(name)
            out = self._claude(path, request, confirmed, session)
            if session and out.returncode != 0:
                out = self._claude(path, request, confirmed, None)  # the old session is gone
            try:
                session_id = json.loads(out.stdout).get("session_id")
            except ValueError:
                session_id = None
            if session_id:
                sessions = self.sessions()
                sessions[name] = session_id
                self.sessions_file.write_text(json.dumps(sessions, indent=2))
            result, pending, error = read_result(out.stdout)
            done = {"name": name, "where": "cloud", "result": result or out.stderr[:500], "pending": pending,
                    "error": error or out.returncode != 0}
        except Exception as exc:  # noqa: BLE001 - the user must hear that it failed
            done = {"name": name, "where": "cloud", "result": f"No pude correr Claude Code: {exc}", "pending": [],
                    "error": True}
        finally:
            with self.lock:
                self.busy.discard(name)
        self.notify(done)

    @staticmethod
    def dev_command(path, port):
        package = path / "package.json"
        if package.exists():
            scripts = json.loads(package.read_text()).get("scripts") or {}
            script = "dev" if "dev" in scripts else "start" if "start" in scripts else None
            if not script:
                return None
            manager = ("bun" if (path / "bun.lock").exists() or (path / "bun.lockb").exists() else
                       "pnpm" if (path / "pnpm-lock.yaml").exists() else
                       "yarn" if (path / "yarn.lock").exists() else "npm")
            return manager, ["run", script, "--", "--port", str(port)]  # vite, next, astro… take --port
        return None

    def run(self, name):
        path = self.path(name)
        if self.alive(name):
            self.caddy(name, self.previews[name][1])  # again: a Caddy restart drops routes added at run time
            return {"running": name, "url": preview_url(name)}
        used = {port for proc, port in self.previews.values() if proc.poll() is None}
        port = next((p for p in PREVIEW_PORTS if p not in used and port_free(p)), None)
        if port is None:
            raise Refused("Ya hay demasiadas vistas previas corriendo; detén alguna")
        command = self.dev_command(path, port)
        if not command:
            raise Refused("No sé cómo correr este proyecto: no tiene script dev ni start")
        manager, args = command
        proc = subprocess.Popen(program(manager, *args), cwd=path, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, start_new_session=True,
                                env={**os.environ, "PORT": str(port)})
        tail, up = [], False
        deadline = time.monotonic() + URL_WAIT
        while time.monotonic() < deadline:
            line = proc.stdout.readline()
            if not line:
                break
            tail.append(ANSI.sub("", line.strip()))
            if find_url(line):
                up = True
                break
        threading.Thread(target=lambda: [None for _ in proc.stdout], daemon=True).start()  # keep draining
        if proc.poll() is not None:
            raise Refused(f"El proyecto se detuvo: {' | '.join(tail[-8:])[:400]}")
        self.previews[name] = (proc, port)
        self.caddy(name, port)
        return {"running": name, "url": preview_url(name), "started": up, "command": f"{manager} {' '.join(args)}"}

    def delete(self, name, confirmed):
        """To /srv/projects/.trash (recoverable), only after the user's yes."""
        if not confirmed:
            raise Refused("Falta la confirmación del usuario (confirmed: true) para borrar el proyecto")
        path = self.path(name)
        if name in self.busy:
            raise Refused(f"Claude Code está trabajando en {name}; espera a que termine")
        if self.alive(name):
            self.stop(name)
        trash = self.root / ".trash"
        trash.mkdir(exist_ok=True)
        target = trash / name
        if target.exists():
            target = trash / f"{name}-{int(time.time())}"
        path.rename(target)
        sessions = self.sessions()
        if sessions.pop(name, None):
            self.sessions_file.write_text(json.dumps(sessions, indent=2))
        return {"deleted": name, "trash": str(target)}

    def stop(self, name):
        if not self.alive(name):
            raise Refused(f"{name} no está corriendo en la nube")
        proc, _ = self.previews.pop(name)
        os.killpg(proc.pid, signal.SIGTERM)  # its own session: npm and the server under it
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
        self.caddy(name, None)
        return {"stopped": name}


def preview_url(name):
    return f"http://{name}.dev.finnip"


def port_free(port):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def caddy_route(name, port):
    """Adds (port) or removes (None) the route <name>.dev.finnip -> 127.0.0.1:port in the running Caddy.
    Dev servers like Vite only answer to their own host name, so Host is rewritten."""
    # ponytail: routes live in Caddy's memory; a Caddy restart drops them until "córrelo" again.
    def call(method, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(CADDY_ADMIN + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read() or b"null")
    route_id = f"dev-{name}"
    try:
        call("DELETE", f"/id/{route_id}")
    except urllib.error.HTTPError:
        pass  # it was not there
    if port is None:
        return
    servers = call("GET", "/config/apps/http/servers")
    server = next(k for k, v in servers.items() if any(l.endswith(":80") for l in v.get("listen", [])))
    route = {"@id": route_id, "match": [{"host": [f"{name}.dev.finnip"]}], "terminal": True,
             "handle": [{"handler": "reverse_proxy", "upstreams": [{"dial": f"127.0.0.1:{port}"}],
                         "headers": {"request": {"set": {"Host": [f"localhost:{port}"]}}}}]}
    call("PUT", f"/config/apps/http/servers/{server}/routes/0", route)  # PUT on an index inserts there


def post_done(done):
    """A finished task to the voice gateway, which has Finnip tell the user."""
    body = json.dumps(done).encode()
    request = urllib.request.Request(f"{GATEWAY}/internal/project_done", data=body, method="POST", headers={
        "Authorization": f"Bearer {os.environ.get('PARTS_API_KEY', '')}", "Content-Type": "application/json"})
    try:
        urllib.request.urlopen(request, timeout=30).read()
    except OSError as error:
        print(f"project_done not delivered: {error}", flush=True)


class Handler(BaseHTTPRequestHandler):
    projects = None

    def do_POST(self):  # noqa: N802 - http.server's name
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            status, body = 200, self.projects.handle(req if isinstance(req, dict) else {})
        except Refused as error:
            status, body = 422, {"error": str(error)}
        except Exception as error:  # noqa: BLE001
            status, body = 500, {"error": f"Error en el servidor de proyectos: {error}"[:300]}
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def address_string(self):  # a Unix socket has no client address
        return "gateway"


class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


def main():
    Handler.projects = Projects()
    if os.path.exists(SOCKET):
        os.unlink(SOCKET)
    server = Server(SOCKET, Handler)
    # Reachable only through its folder (data/runner: finnip and group 10000, mode 750), i.e. the gateway.
    os.chmod(SOCKET, 0o666)
    print(f"finnip-runner on {SOCKET}, projects in {ROOT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
