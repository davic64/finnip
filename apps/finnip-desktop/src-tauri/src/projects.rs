// Voice projects ("Finnip, nuevo proyecto…", "agrégale…", "córrelo"): fixed actions on folders under
// ~/Projects, asked by the overlay page on behalf of the server. Nothing here runs a command the server
// wrote: project names, repositories and allowed commands are checked, and every program gets its
// arguments without a shell interpreting them.
use std::{
    collections::{HashMap, HashSet},
    fs,
    io::{BufRead, BufReader, Read},
    os::unix::process::CommandExt,
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::{mpsc, Arc, Mutex},
    thread,
    time::{Duration, Instant},
};

use serde::Deserialize;
use serde_json::{json, Value};

const URL_WAIT: Duration = Duration::from_secs(90); // a dev server's first build can be slow
const MAX_REQUEST: usize = 4000;
// Appended to Claude Code's system prompt: its last message is what Finnip reads out. It works in bypass
// mode (no permission prompts) and stops on its own before anything important; Finnip asks the user.
pub const SYSTEM: &str = "Te habla Finnip, el asistente de voz del usuario, con sus órdenes. Trabajas sin pedir \
permiso para editar, instalar dependencias del proyecto o correr comandos. Pero ANTES de algo importante o \
irreversible (borrar archivos o datos que no creaste en esta tarea, git push o reescribir historial, publicar o \
desplegar, gastar dinero o usar servicios de pago, tocar credenciales o secretos, instalar herramientas globales \
del sistema) NO lo hagas: termina con una línea que empiece con 'CONFIRMAR:' diciendo qué harías y por qué. Si la \
orden empieza con 'Confirmado:', el usuario ya lo autorizó: hazlo. Al terminar, responde en español con un resumen \
breve (2 o 3 frases, sin código ni rutas largas) de lo que hiciste y de lo que falte.";
/// Blocked unless the user confirmed by voice, even if Claude Code forgets to ask first.
pub const NEEDS_CONFIRMATION: [&str; 4] = ["Bash(git push:*)", "Bash(git reset --hard:*)", "Bash(sudo:*)", "Bash(npm publish:*)"];

#[derive(Deserialize, Default)]
#[serde(default)]
pub struct Request {
    pub action: String,
    pub name: String,
    pub repo: String,
    pub request: String,
    /// The user said yes by voice to what Claude Code asked: no NEEDS_CONFIRMATION block this time.
    pub confirmed: bool,
    /// "cloud": only "open" reaches the Mac for a server project (Zed over SSH to the host `finnip`).
    #[serde(rename = "where")]
    pub place: String,
    /// A project outside ~/Projects, relative to home ("Documents/clientes/tienda"): open, task, run, stop.
    pub path: String,
    /// Task: the user points at something on screen ("haz esto más grande").
    pub point: bool,
    /// Set by main.rs only (never from the page): the capture around the pointer and where the pointer is.
    #[serde(skip)]
    pub shot: Option<Shot>,
}

/// A capture of the screen around the mouse pointer (JPEG) and the pointer's place in it, in percent.
pub struct Shot {
    pub file: PathBuf,
    pub x: u32,
    pub y: u32,
}

/// The note that tells Claude Code what the user points at, before their words.
pub fn pointing(file: &str, x: u32, y: u32) -> String {
    format!("[El usuario señala algo en su pantalla con el puntero del mouse mientras habla. Captura de la zona \
alrededor del puntero: {file} (el puntero está a {x}% desde la izquierda y {y}% desde arriba). Ábrela con Read \
para ver a qué se refiere con «esto» o «aquí».] ")
}

/// Called with a finished task: {name, result, pending, error}.
pub type OnDone = Arc<dyn Fn(Value) + Send + Sync>;

pub struct Projects {
    home: PathBuf,
    root: PathBuf, // ~/Projects: new projects, and the only ones that can be deleted
    sessions_file: PathBuf, // project -> Claude Code session id, so each order continues the last one
    busy: Mutex<HashSet<String>>,
    running: Mutex<HashMap<String, (Child, Option<String>)>>, // dev servers and their URL
}

/// "tienda", "mi-app_2": lowercase letters, digits, "-" and "_", starting with a letter or digit.
pub fn valid_name(name: &str) -> bool {
    let mut chars = name.chars();
    matches!(chars.next(), Some(c) if c.is_ascii_lowercase() || c.is_ascii_digit())
        && name.len() <= 60
        && chars.all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '-' || c == '_')
}

/// "owner/name" or a github.com URL -> "owner/name" for `gh repo clone`; None for anything else.
pub fn valid_repo(repo: &str) -> Option<String> {
    let repo = repo.trim();
    let repo = repo.strip_prefix("https://github.com/").unwrap_or(repo);
    let repo = repo.trim_end_matches('/').trim_end_matches(".git");
    let ok = |s: &str| !s.is_empty() && !s.starts_with('.') && s.chars().all(|c| c.is_ascii_alphanumeric() || "-_.".contains(c));
    match repo.split('/').collect::<Vec<_>>()[..] {
        [owner, name] if ok(owner) && ok(name) => Some(format!("{owner}/{name}")),
        _ => None,
    }
}

/// A program run through the user's login shell for its PATH (fnm, bun, ~/.local/bin), with the
/// arguments passed as "$@": the shell never parses them.
fn program(name: &str, args: &[&str]) -> Command {
    let mut command = Command::new("/bin/zsh");
    command.args(["-lc", "exec \"$0\" \"$@\"", name]).args(args);
    command
}

fn strip_ansi(line: &str) -> String {
    let mut out = String::new();
    let mut chars = line.chars();
    while let Some(c) = chars.next() {
        if c == '\u{1b}' {
            for c in chars.by_ref() {
                if c.is_ascii_alphabetic() {
                    break;
                }
            }
        } else {
            out.push(c);
        }
    }
    out
}

/// The first local URL a dev server prints ("Local:   http://localhost:5173/").
pub fn find_url(line: &str) -> Option<String> {
    let line = strip_ansi(line);
    let start = line.find("http://localhost:").or_else(|| line.find("http://127.0.0.1:"))?;
    let url: String = line[start..].chars().take_while(|c| !c.is_whitespace()).collect();
    Some(url.trim_end_matches(['.', ',', ')']).to_string())
}

/// Claude Code's JSON result -> (its last message, what needs the user's yes, error). What needs a yes:
/// its "CONFIRMAR:" lines and the commands NEEDS_CONFIRMATION blocked.
pub fn read_result(stdout: &str) -> (String, Vec<String>, bool) {
    let Ok(value) = serde_json::from_str::<Value>(stdout.trim()) else {
        return (stdout.chars().take(500).collect(), vec![], true);
    };
    let result = value["result"].as_str().unwrap_or("").to_string();
    let mut pending: Vec<String> = result
        .lines()
        .filter_map(|line| line.trim().trim_start_matches(['*', '-', ' ']).strip_prefix("CONFIRMAR:"))
        .map(|what| what.trim().to_string())
        .collect();
    pending.extend(value["permission_denials"].as_array().into_iter().flatten().map(|d| {
        match d["tool_input"]["command"].as_str() {
            Some(command) => format!("correr {command}"),
            None => d["tool_name"].as_str().unwrap_or("?").to_string(),
        }
    }));
    (result, pending, value["is_error"].as_bool().unwrap_or(false))
}

impl Projects {
    pub fn new(home: PathBuf, sessions_file: PathBuf) -> Self {
        let root = home.join("Projects");
        Self { home, root, sessions_file, busy: Mutex::default(), running: Mutex::default() }
    }

    /// Where Finnip may work: ~/Projects and ~/Documents, and nothing outside them.
    fn roots(&self) -> Vec<PathBuf> {
        [self.root.clone(), self.home.join("Documents")].into_iter().filter_map(|r| r.canonicalize().ok()).collect()
    }

    /// The project a request names -> (its key: the name, or the path from home; its folder).
    /// A path is resolved (symlinks and "..") before checking that it is inside a root.
    fn resolve(&self, req: &Request) -> Result<(String, PathBuf), String> {
        let rel = req.path.trim().trim_start_matches("~/").trim_start_matches('/');
        if rel.is_empty() {
            return Ok((req.name.clone(), self.existing(&req.name)?));
        }
        let path = self.home.join(rel).canonicalize().map_err(|_| format!("No encontré la carpeta {rel}"))?;
        if !path.is_dir() || !self.roots().iter().any(|root| path.starts_with(root) && &path != root) {
            return Err("Solo trabajo en carpetas dentro de ~/Projects o ~/Documents".into());
        }
        let home = self.home.canonicalize().unwrap_or_else(|_| self.home.clone());
        let key = path.strip_prefix(&home).unwrap_or(&path).to_string_lossy().to_string();
        Ok((key, path))
    }

    /// Folders under the roots whose name contains `query` (case-insensitive), at most 4 levels down.
    fn find(&self, query: &str) -> Result<Value, String> {
        let query = query.trim().to_lowercase();
        if query.is_empty() {
            return Err("Falta qué carpeta buscar".into());
        }
        fn walk(dir: &Path, depth: u8, query: &str, home: &Path, found: &mut Vec<String>) {
            if depth == 0 || found.len() >= 10 {
                return;
            }
            for entry in fs::read_dir(dir).into_iter().flatten().flatten() {
                let name = entry.file_name().to_string_lossy().to_string();
                let path = entry.path();
                if name.starts_with('.') || name == "node_modules" || name == "target" || !path.is_dir() {
                    continue;
                }
                if name.to_lowercase().contains(query) && found.len() < 10 {
                    found.push(path.strip_prefix(home).unwrap_or(&path).to_string_lossy().to_string());
                }
                walk(&path, depth - 1, query, home, found);
            }
        }
        let mut found = Vec::new();
        for root in self.roots() {
            walk(&root, 4, &query, &self.home.canonicalize().unwrap_or(self.home.clone()), &mut found);
        }
        Ok(json!({ "found": found }))
    }

    /// To the Trash (recoverable), only from ~/Projects, only after the user's yes.
    fn delete(&self, req: &Request) -> Result<Value, String> {
        if !req.confirmed {
            return Err("Falta la confirmación del usuario (confirmed: true) para borrar el proyecto".into());
        }
        if !req.path.trim().is_empty() {
            return Err("Solo borro proyectos de ~/Projects".into());
        }
        let path = self.existing(&req.name)?;
        if let Some((mut child, _)) = self.running.lock().unwrap().remove(&req.name) {
            let _ = Command::new("/bin/kill").args(["-TERM", &format!("-{}", child.id())]).status();
            let _ = child.wait();
        }
        let trash = self.home.join(".Trash");
        let _ = fs::create_dir_all(&trash);
        let mut target = trash.join(&req.name);
        if target.exists() {
            let stamp = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map_or(0, |d| d.as_secs());
            target = trash.join(format!("{}-{stamp}", req.name));
        }
        fs::rename(&path, &target).map_err(|e| format!("No pude mandarlo a la Papelera: {e}"))?;
        let mut sessions = self.sessions();
        if sessions.remove(&req.name).is_some() {
            if let Ok(text) = serde_json::to_string_pretty(&sessions) {
                let _ = fs::write(&self.sessions_file, text);
            }
        }
        Ok(json!({ "deleted": req.name, "trash": true }))
    }

    fn path(&self, name: &str) -> Result<PathBuf, String> {
        if !valid_name(name) {
            return Err("Nombre de proyecto inválido: minúsculas, números, - y _".into());
        }
        Ok(self.root.join(name))
    }

    fn existing(&self, name: &str) -> Result<PathBuf, String> {
        let path = self.path(name)?;
        if !path.is_dir() {
            return Err(format!("No existe el proyecto {name}"));
        }
        Ok(path)
    }

    fn sessions(&self) -> HashMap<String, String> {
        fs::read_to_string(&self.sessions_file).ok().and_then(|s| serde_json::from_str(&s).ok()).unwrap_or_default()
    }

    fn save_session(&self, name: &str, id: &str) {
        let mut sessions = self.sessions();
        sessions.insert(name.into(), id.into());
        if let Ok(text) = serde_json::to_string_pretty(&sessions) {
            let _ = fs::write(&self.sessions_file, text);
        }
    }

    pub fn handle(self: &Arc<Self>, req: Request, on_done: OnDone) -> Result<Value, String> {
        fs::create_dir_all(&self.root).map_err(|e| e.to_string())?;
        match req.action.as_str() {
            "list" => Ok(self.list()),
            "create" => self.create(&req),
            "open" if req.place == "cloud" => {
                if !valid_name(&req.name) {
                    return Err("Nombre de proyecto inválido".into());
                }
                let url = format!("ssh://finnip/srv/projects/{}", req.name);
                program("zed", &[&url]).spawn().map_err(|e| format!("No pude abrir Zed: {e}"))?;
                Ok(json!({ "opened": req.name, "where": "cloud" }))
            }
            _ if req.place == "cloud" => Err("Esa acción en la nube la hace el servidor".into()),
            "open" => {
                let (key, path) = self.resolve(&req)?;
                program("zed", &[&path.to_string_lossy()]).spawn().map_err(|e| format!("No pude abrir Zed: {e}"))?;
                Ok(json!({ "opened": key }))
            }
            "find" => self.find(&req.name),
            "delete" => self.delete(&req),
            "task" => self.task(req, on_done),
            "run" => self.run(&req),
            "stop" => {
                let (key, _) = self.resolve(&req)?;
                let (mut child, _) = self.running.lock().unwrap().remove(&key).ok_or(format!("{key} no está corriendo"))?;
                // The dev server is its own process group (npm -> vite): stop all of it.
                let _ = Command::new("/bin/kill").args(["-TERM", &format!("-{}", child.id())]).status();
                let _ = child.wait();
                Ok(json!({ "stopped": key }))
            }
            other => Err(format!("Acción desconocida: {other}")),
        }
    }

    fn list(&self) -> Value {
        let busy = self.busy.lock().unwrap().clone();
        let running = self.running.lock().unwrap();
        let mut projects: Vec<Value> = fs::read_dir(&self.root)
            .into_iter()
            .flatten()
            .flatten()
            .filter(|e| e.path().is_dir())
            .filter_map(|e| e.file_name().into_string().ok())
            .filter(|name| !name.starts_with('.'))
            .map(|name| {
                json!({
                    "name": name,
                    "git": self.root.join(&name).join(".git").exists(),
                    "working": busy.contains(&name),
                    "running": running.get(&name).map(|(_, url)| url.clone().unwrap_or_default()),
                })
            })
            .collect();
        projects.sort_by(|a, b| a["name"].as_str().cmp(&b["name"].as_str()));
        json!({ "root": self.root, "projects": projects })
    }

    fn create(&self, req: &Request) -> Result<Value, String> {
        let path = self.path(&req.name)?;
        if path.exists() {
            return Err(format!("Ya existe el proyecto {}", req.name));
        }
        let path_arg = path.to_string_lossy().to_string();
        let output = if req.repo.trim().is_empty() {
            fs::create_dir_all(&path).map_err(|e| e.to_string())?;
            program("git", &["init", "-q", &path_arg]).output()
        } else {
            let repo = valid_repo(&req.repo).ok_or("Repositorio inválido: usa dueño/nombre o su URL de GitHub")?;
            program("gh", &["repo", "clone", &repo, &path_arg]).output()
        }
        .map_err(|e| e.to_string())?;
        if !output.status.success() {
            let _ = fs::remove_dir(&path); // only if empty: a failed clone leaves nothing behind
            return Err(String::from_utf8_lossy(&output.stderr).chars().take(300).collect());
        }
        let _ = program("zed", &[&path_arg]).spawn();
        Ok(json!({ "created": req.name, "path": path, "cloned": !req.repo.trim().is_empty() }))
    }

    fn task(self: &Arc<Self>, req: Request, on_done: OnDone) -> Result<Value, String> {
        let (name, path) = self.resolve(&req)?;
        let mut request = req.request.trim().to_string();
        if request.is_empty() || request.len() > MAX_REQUEST {
            return Err("Falta lo que hay que hacer en el proyecto".into());
        }
        if let Some(shot) = &req.shot {
            // Inside the project (Claude Code's working folder), kept out of git.
            let dir = path.join(".finnip");
            fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
            let name = shot.file.file_name().ok_or("Captura inválida")?;
            fs::copy(&shot.file, dir.join(name)).map_err(|e| format!("No pude guardar la captura: {e}"))?;
            let _ = fs::remove_file(&shot.file);
            let exclude = path.join(".git/info/exclude");
            if exclude.exists() && !fs::read_to_string(&exclude).unwrap_or_default().contains(".finnip/") {
                let _ = fs::write(&exclude, fs::read_to_string(&exclude).unwrap_or_default() + "\n.finnip/\n");
            }
            request = pointing(&format!(".finnip/{}", name.to_string_lossy()), shot.x, shot.y) + &request;
        }
        if !self.busy.lock().unwrap().insert(name.clone()) {
            return Err(format!("Claude Code ya está trabajando en {name}"));
        }
        let this = Arc::clone(self);
        let started = name.clone();
        thread::spawn(move || {
            let session = this.sessions().get(&name).cloned();
            let attempt = |resume: Option<&String>| {
                let mut args = vec!["-p", &request, "--output-format", "json", "--permission-mode", "bypassPermissions",
                                    "--setting-sources", "project", "--append-system-prompt", SYSTEM];
                if let Some(id) = resume {
                    args.extend(["--resume", id]);
                }
                if !req.confirmed {
                    args.push("--disallowedTools");
                    args.extend(NEEDS_CONFIRMATION);
                }
                program("claude", &args).current_dir(&path).stdin(Stdio::null()).output()
            };
            let mut output = attempt(session.as_ref());
            if session.is_some() && output.as_ref().map_or(true, |o| !o.status.success()) {
                output = attempt(None); // the old session is gone: start a new one
            }
            let done = match output {
                Ok(out) => {
                    let stdout = String::from_utf8_lossy(&out.stdout);
                    if let Some(id) = serde_json::from_str::<Value>(stdout.trim()).ok().and_then(|v| v["session_id"].as_str().map(String::from)) {
                        this.save_session(&name, &id);
                    }
                    let (result, pending, error) = read_result(&stdout);
                    let error = error || !out.status.success();
                    let result = if result.is_empty() { String::from_utf8_lossy(&out.stderr).chars().take(500).collect() } else { result };
                    json!({ "name": name, "result": result, "pending": pending, "error": error })
                }
                Err(e) => json!({ "name": name, "result": format!("No pude correr Claude Code: {e}"), "pending": [], "error": true }),
            };
            this.busy.lock().unwrap().remove(&name);
            on_done(done);
        });
        Ok(json!({ "started": started }))
    }

    /// How to start the project's dev server, from its files.
    fn dev_command(path: &Path) -> Option<(&'static str, Vec<&'static str>)> {
        if let Ok(text) = fs::read_to_string(path.join("package.json")) {
            let scripts = serde_json::from_str::<Value>(&text).ok()?["scripts"].clone();
            let script = if scripts["dev"].is_string() { "dev" } else if scripts["start"].is_string() { "start" } else { return None };
            let manager = if path.join("bun.lock").exists() || path.join("bun.lockb").exists() {
                "bun"
            } else if path.join("pnpm-lock.yaml").exists() {
                "pnpm"
            } else if path.join("yarn.lock").exists() {
                "yarn"
            } else {
                "npm"
            };
            return Some((manager, vec!["run", script]));
        }
        path.join("Cargo.toml").exists().then(|| ("cargo", vec!["run"]))
    }

    fn run(&self, req: &Request) -> Result<Value, String> {
        let (name, path) = self.resolve(req)?;
        let name = name.as_str();
        if let Some((_, url)) = self.running.lock().unwrap().get(name) {
            return Ok(json!({ "running": name, "url": url }));
        }
        let (manager, args) = Self::dev_command(&path).ok_or("No sé cómo correr este proyecto: no tiene script dev ni start")?;
        let mut child = program(manager, &args)
            .current_dir(&path)
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .process_group(0)
            .spawn()
            .map_err(|e| e.to_string())?;
        // Both outputs are read to the end (a full pipe would block the server); lines go to the channel.
        let (lines, rx) = mpsc::channel::<String>();
        fn drain(out: impl Read + Send + 'static, lines: mpsc::Sender<String>) {
            thread::spawn(move || {
                for line in BufReader::new(out).lines().map_while(Result::ok) {
                    let _ = lines.send(line);
                }
            });
        }
        drain(child.stdout.take().unwrap(), lines.clone());
        drain(child.stderr.take().unwrap(), lines);
        let deadline = Instant::now() + URL_WAIT;
        let mut url = None;
        let mut tail = Vec::new();
        while url.is_none() {
            let left = deadline.saturating_duration_since(Instant::now());
            match rx.recv_timeout(left.max(Duration::from_millis(1))) {
                Ok(line) => {
                    url = find_url(&line);
                    tail.push(strip_ansi(&line));
                }
                Err(_) => break, // time is up, or the server exited
            }
            if Instant::now() >= deadline {
                break;
            }
        }
        thread::spawn(move || for _ in rx {}); // keep draining after the URL
        if let Ok(Some(status)) = child.try_wait() {
            let last: Vec<String> = tail.iter().rev().take(8).rev().cloned().collect();
            return Err(format!("El proyecto se detuvo ({status}): {}", last.join(" | ").chars().take(400).collect::<String>()));
        }
        if let Some(url) = &url {
            let _ = Command::new("/usr/bin/open").arg(url).spawn();
        }
        self.running.lock().unwrap().insert(name.to_string(), (child, url.clone()));
        Ok(json!({ "running": name, "url": url, "command": format!("{manager} {}", args.join(" ")) }))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn names_repos_and_commands_are_checked() {
        assert!(valid_name("tienda") && valid_name("mi-app_2") && valid_name("2048"));
        assert!(!valid_name("") && !valid_name("../etc") && !valid_name("Tienda") && !valid_name("-x") && !valid_name("a b"));
        assert_eq!(valid_repo("davic64/finnip").as_deref(), Some("davic64/finnip"));
        assert_eq!(valid_repo("https://github.com/davic64/finnip.git").as_deref(), Some("davic64/finnip"));
        assert_eq!(valid_repo("../x"), None);
        assert_eq!(valid_repo("a/b; rm -rf ~"), None);
        assert_eq!(valid_repo("https://evil.com/a/b"), None);
    }

    #[test]
    fn dev_server_urls_are_found_through_colors() {
        assert_eq!(find_url("  \u{1b}[32m➜\u{1b}[39m  Local:   \u{1b}[36mhttp://localhost:\u{1b}[1m5173\u{1b}[22m/\u{1b}[39m").as_deref(),
                   Some("http://localhost:5173/"));
        assert_eq!(find_url("Listening on http://127.0.0.1:3000.").as_deref(), Some("http://127.0.0.1:3000"));
        assert_eq!(find_url("compiling…"), None);
    }

    #[test]
    fn pending_commands_come_from_permission_denials() {
        let out = r#"{"result":"Listo el login.\nCONFIRMAR: subir los cambios con git push a main","is_error":false,
            "permission_denials":[{"tool_name":"Bash","tool_input":{"command":"git push"}},{"tool_name":"WebFetch","tool_input":{}}]}"#;
        let (_, pending, error) = read_result(out);
        assert_eq!(pending, ["subir los cambios con git push a main", "correr git push", "WebFetch"]);
        assert!(!error);
        assert!(read_result("not json").2);
    }

    #[test]
    fn create_and_list_stay_inside_the_root() {
        let home = std::env::temp_dir().join(format!("finnip-projects-test-{}", std::process::id()));
        let _ = fs::remove_dir_all(&home);
        let projects = Arc::new(Projects::new(home.clone(), home.join(".sessions.json")));
        let noop: OnDone = Arc::new(|_| {});
        let ask = |action: &str, name: &str, path: &str, confirmed: bool| Request {
            action: action.into(), name: name.into(), path: path.into(), confirmed, ..Default::default()
        };
        assert!(projects.handle(ask("create", "../fuera", "", false), noop.clone()).is_err());
        fs::create_dir_all(home.join("Projects/tienda")).unwrap();
        fs::create_dir_all(home.join("Documents/clientes/Tienda Vieja")).unwrap();
        fs::create_dir_all(home.join("Secret")).unwrap();
        let listed = projects.handle(ask("list", "", "", false), noop.clone()).unwrap();
        assert_eq!(listed["projects"][0]["name"], "tienda");
        // Documents is allowed; anything that resolves outside the roots is not.
        let (key, _) = projects.resolve(&ask("open", "", "Documents/clientes/Tienda Vieja", false)).unwrap();
        assert_eq!(key, "Documents/clientes/Tienda Vieja");
        for bad in ["Documents/../Secret", "Secret", "Documents", "/etc", "Documents/nope"] {
            assert!(projects.resolve(&ask("open", "", bad, false)).is_err(), "{bad}");
        }
        let found = projects.handle(ask("find", "tienda", "", false), noop.clone()).unwrap();
        assert_eq!(found["found"].as_array().unwrap().len(), 2);
        // Deleting: only with a yes, only ~/Projects, and to the Trash.
        assert!(projects.handle(ask("delete", "tienda", "", false), noop.clone()).is_err());
        assert!(projects.handle(ask("delete", "", "Documents/clientes", true), noop.clone()).is_err());
        projects.handle(ask("delete", "tienda", "", true), noop).unwrap();
        assert!(!home.join("Projects/tienda").exists() && home.join(".Trash/tienda").exists());
        let _ = fs::remove_dir_all(&home);
    }
}
