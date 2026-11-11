// Finnip for macOS: a transparent, click-through overlay that shows the voice gateway's page
// (?desktop=1 mode), plus a menu bar icon, a global shortcut and the user's preferences.
// The remote page gets almost no native API: this side talks to it through `eval` of a tiny hook
// (window.finnipDesktop), and the page may call one command, part_box, to say where an open 3D part is
// (the only place the overlay then takes the mouse). The local Preferences window may call the rest.
use std::{
    fs,
    path::{Path, PathBuf},
    sync::{
        atomic::{AtomicBool, Ordering},
        Mutex,
    },
    thread,
    time::Duration,
};

mod projects;

use std::sync::Arc;

use serde::{Deserialize, Serialize};
use tauri::{
    image::Image,
    ipc::CapabilityBuilder,
    menu::{CheckMenuItem, Menu, MenuItem, PredefinedMenuItem, Submenu},
    tray::TrayIconBuilder,
    AppHandle, LogicalPosition, LogicalSize, Manager, Monitor, WebviewUrl, WebviewWindow, WebviewWindowBuilder,
};
use tauri_plugin_autostart::{MacosLauncher, ManagerExt};
use tauri_plugin_global_shortcut::{GlobalShortcutExt, ShortcutState};

/// Gateway URL, fixed at build time (FINNIP_URL) so the tailnet name stays out of the repo.
const FINNIP_URL: &str = match option_env!("FINNIP_URL") {
    Some(url) => url,
    None => "https://finnip.invalid",
};
const DEFAULT_SHORTCUT: &str = "Alt+Super+F";
const TRAY: &str = "finnip";
const WATCH_EVERY: Duration = Duration::from_secs(5); // monitors every tick, gateway health every other
const CURSOR_EVERY: Duration = Duration::from_millis(40); // while a part is open
const CURSOR_IDLE: Duration = Duration::from_millis(250);

// --- preferences -----------------------------------------------------------------------------------

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(default)]
struct Settings {
    /// Monitor chosen in the menu (monitor_id: name and position); None = the primary one.
    display: Option<String>,
    shortcut: String,
    /// Listening for "Finnip" turned off in the menu; the shortcut still opens the mic for one phrase.
    muted: bool,
}

impl Default for Settings {
    fn default() -> Self {
        Self { display: None, shortcut: DEFAULT_SHORTCUT.into(), muted: false }
    }
}

/// Missing or damaged file: defaults (never fails, the app must start anyway).
fn load_settings(path: &Path) -> Settings {
    fs::read_to_string(path).ok().and_then(|s| serde_json::from_str(&s).ok()).unwrap_or_default()
}

/// Atomic: a crash mid-write leaves the previous file, not half of one.
fn save_settings(path: &Path, settings: &Settings) -> std::io::Result<()> {
    if let Some(dir) = path.parent() {
        fs::create_dir_all(dir)?;
    }
    let tmp = path.with_extension("json.tmp");
    fs::write(&tmp, serde_json::to_vec_pretty(settings)?)?;
    fs::rename(tmp, path)
}

/// "Alt+Super+F": at least one modifier and exactly one key, last.
fn valid_shortcut(shortcut: &str) -> bool {
    let parts: Vec<&str> = shortcut.split('+').collect();
    let (key, mods) = parts.split_last().expect("split always yields one part");
    !mods.is_empty()
        && !key.is_empty()
        && !matches!(*key, "Super" | "Alt" | "Control" | "Shift")
        && mods.iter().all(|m| matches!(*m, "Super" | "Alt" | "Control" | "Shift"))
}

// --- state -----------------------------------------------------------------------------------------

struct Finnip {
    path: PathBuf,
    settings: Mutex<Settings>,
    muted: AtomicBool,
    visible: AtomicBool,
    online: AtomicBool,
    shown_on: Mutex<Option<String>>, // monitor the overlay is on now
    /// The open 3D part's box in the overlay ([x, y, width, height], CSS pixels), or None.
    part_box: Mutex<Option<[f64; 4]>>,
}

/// muted: the page loads with the mic closed (no flash of the macOS mic indicator).
fn page_url(muted: bool) -> String {
    format!("{}/?desktop=1{}", FINNIP_URL.trim_end_matches('/'), if muted { "&muted=1" } else { "" })
}

fn overlay(app: &AppHandle) -> Option<WebviewWindow> {
    app.get_webview_window("overlay")
}

/// One-way call into the page's hook; the page cannot call back.
fn page(app: &AppHandle, js: &str) {
    if let Some(window) = overlay(app) {
        let _ = window.eval(js);
    }
}

/// Also with listening off: the page opens the mic for one phrase and closes it again.
fn talk(app: &AppHandle) {
    page(app, "window.finnipDesktop?.talk()");
}

// --- monitors --------------------------------------------------------------------------------------

/// Name plus position: two identical monitors share a name (the user has two HUAWEI AD80HW).
fn monitor_id(monitor: &Monitor) -> String {
    let pos = monitor.position();
    format!("{}@{},{}", monitor.name().map(String::as_str).unwrap_or("Pantalla"), pos.x, pos.y)
}

/// Menu labels, left to right; a repeated name gets " · 1", " · 2".
fn monitor_labels(monitors: &[Monitor], primary: Option<&str>) -> Vec<(String, String)> {
    let mut sorted: Vec<&Monitor> = monitors.iter().collect();
    sorted.sort_by_key(|m| (m.position().x, m.position().y));
    let name = |m: &Monitor| m.name().cloned().unwrap_or_else(|| "Pantalla".into());
    let mut seen = std::collections::HashMap::<String, usize>::new();
    sorted
        .iter()
        .map(|m| {
            let base = name(m);
            let repeated = sorted.iter().filter(|o| name(o) == base).count() > 1;
            let n = seen.entry(base.clone()).and_modify(|n| *n += 1).or_insert(1);
            let mut label = if repeated { format!("{base} · {n}") } else { base };
            let id = monitor_id(m);
            if primary == Some(id.as_str()) {
                label.push_str(" (principal)");
            }
            (id, label)
        })
        .collect()
}

/// The chosen monitor while it is connected, else the primary one.
fn target_monitor(app: &AppHandle) -> Option<Monitor> {
    let wanted = app.state::<Finnip>().settings.lock().unwrap().display.clone();
    let monitors = app.available_monitors().ok()?;
    wanted
        .and_then(|id| monitors.into_iter().find(|m| monitor_id(m) == id))
        .or_else(|| app.primary_monitor().ok().flatten())
}

/// Moves the overlay onto the target monitor. Size first: a window still as big as the previous
/// (larger) monitor hung off a smaller one, like the iPad (Sidecar), into the screen below it. Applied
/// again a moment later, once macOS has switched the window to the new monitor's scale.
fn place_overlay(app: &AppHandle) {
    let (Some(window), Some(monitor)) = (overlay(app), target_monitor(app)) else { return };
    let scale = monitor.scale_factor();
    let pos = monitor.position().to_logical::<f64>(scale);
    let size = monitor.size().to_logical::<f64>(scale);
    let apply = move |window: &WebviewWindow| {
        let _ = window.set_size(LogicalSize::new(size.width, size.height));
        let _ = window.set_position(LogicalPosition::new(pos.x, pos.y));
    };
    apply(&window);
    let (later, handle) = (window.clone(), app.clone());
    thread::spawn(move || {
        thread::sleep(Duration::from_millis(400));
        let _ = handle.run_on_main_thread(move || apply(&later));
    });
    *app.state::<Finnip>().shown_on.lock().unwrap() = Some(monitor_id(&monitor));
}

// --- menu bar --------------------------------------------------------------------------------------

fn build_menu(app: &AppHandle) -> tauri::Result<Menu<tauri::Wry>> {
    let state = app.state::<Finnip>();
    let muted = state.muted.load(Ordering::SeqCst);
    let status = if !state.online.load(Ordering::SeqCst) {
        "Sin conexión con Finnip"
    } else if muted {
        "Escucha desactivada"
    } else {
        "Escuchando «Finnip»"
    };
    let current = state.shown_on.lock().unwrap().clone();
    let primary = app.primary_monitor()?.map(|m| monitor_id(&m));
    let screens = Submenu::with_id(app, "screens", "Pantalla", true)?;
    for (id, label) in monitor_labels(&app.available_monitors()?, primary.as_deref()) {
        let on = current.as_deref() == Some(id.as_str());
        screens.append(&CheckMenuItem::with_id(app, format!("screen:{id}"), label, true, on, None::<&str>)?)?;
    }
    let autostart = app.autolaunch().is_enabled().unwrap_or(false);
    Menu::with_items(
        app,
        &[
            &MenuItem::with_id(app, "status", status, false, None::<&str>)?,
            &PredefinedMenuItem::separator(app)?,
            &CheckMenuItem::with_id(app, "show", "Mostrar Finnip", true, state.visible.load(Ordering::SeqCst), None::<&str>)?,
            &CheckMenuItem::with_id(app, "mute", "Escuchar «Finnip»", true, !muted, None::<&str>)?,
            &screens,
            &PredefinedMenuItem::separator(app)?,
            &MenuItem::with_id(app, "panel", "Modos y rutinas…", true, None::<&str>)?,
            &MenuItem::with_id(app, "prefs", "Preferencias…", true, Some("CmdOrCtrl+,"))?,
            &CheckMenuItem::with_id(app, "autostart", "Abrir al iniciar sesión", true, autostart, None::<&str>)?,
            &PredefinedMenuItem::separator(app)?,
            &MenuItem::with_id(app, "quit", "Salir de Finnip", true, Some("CmdOrCtrl+Q"))?,
        ],
    )
}

fn tray_icon(app: &AppHandle) -> Image<'static> {
    let state = app.state::<Finnip>();
    let bytes: &'static [u8] = if !state.online.load(Ordering::SeqCst) {
        include_bytes!("../icons/tray-offline.png")
    } else if state.muted.load(Ordering::SeqCst) {
        include_bytes!("../icons/tray-muted.png")
    } else {
        include_bytes!("../icons/tray.png")
    };
    Image::from_bytes(bytes).expect("bundled tray icon")
}

/// Rebuilds menu and icon from the state (menus live on the main thread on macOS).
fn refresh_tray(app: &AppHandle) {
    let handle = app.clone();
    let _ = app.run_on_main_thread(move || {
        let Some(tray) = handle.tray_by_id(TRAY) else { return };
        if let Ok(menu) = build_menu(&handle) {
            let _ = tray.set_menu(Some(menu));
        }
        let _ = tray.set_icon(Some(tray_icon(&handle)));
        let _ = tray.set_icon_as_template(true);
    });
}

fn on_menu(app: &AppHandle, id: &str) {
    let state = app.state::<Finnip>();
    match id {
        "show" => {
            let on = !state.visible.load(Ordering::SeqCst);
            state.visible.store(on, Ordering::SeqCst);
            page(app, &format!("window.finnipDesktop?.visible({on})"));
        }
        "mute" => {
            let on = !state.muted.load(Ordering::SeqCst);
            state.muted.store(on, Ordering::SeqCst);
            page(app, &format!("window.finnipDesktop?.mute({on})"));
            let mut settings = state.settings.lock().unwrap();
            settings.muted = on;
            let _ = save_settings(&state.path, &settings);
        }
        "prefs" => open_prefs(app),
        // The panel (modes and routines) in the default browser: it needs clicks and typing.
        "panel" => {
            let _ = std::process::Command::new("open")
                .arg(format!("{}/panel.html", FINNIP_URL.trim_end_matches('/')))
                .spawn();
        }
        "autostart" => {
            let launcher = app.autolaunch();
            let _ = if launcher.is_enabled().unwrap_or(false) { launcher.disable() } else { launcher.enable() };
        }
        "quit" => app.exit(0),
        screen if screen.starts_with("screen:") => {
            let name = screen["screen:".len()..].to_string();
            {
                let mut settings = state.settings.lock().unwrap();
                settings.display = Some(name);
                let _ = save_settings(&state.path, &settings);
            }
            place_overlay(app);
        }
        _ => {}
    }
    refresh_tray(app);
}

// --- background watch: monitors and gateway --------------------------------------------------------

fn gateway_up() -> bool {
    // ponytail: curl ships with macOS; a Rust HTTP client would add a TLS stack for one GET every 10 s.
    let health = format!("{}/health", FINNIP_URL.trim_end_matches('/'));
    std::process::Command::new("/usr/bin/curl")
        .args(["-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "5", &health])
        .output()
        .map(|out| out.stdout == b"200")
        .unwrap_or(false)
}

fn watch(app: AppHandle) {
    let mut tick = 0u64;
    loop {
        thread::sleep(WATCH_EVERY);
        tick += 1;
        let state = app.state::<Finnip>();
        let wanted = target_monitor(&app).map(|m| monitor_id(&m));
        if wanted != *state.shown_on.lock().unwrap() {
            // the chosen monitor came back, or went away and the primary takes over
            let handle = app.clone();
            let _ = app.run_on_main_thread(move || place_overlay(&handle));
            refresh_tray(&app);
        }
        if tick % 2 == 0 {
            let up = gateway_up();
            let was = state.online.swap(up, Ordering::SeqCst);
            if up != was {
                if up {
                    // the page may have failed to load while the gateway was down: load it again
                    if let (Some(window), Ok(url)) = (overlay(&app), page_url(state.muted.load(Ordering::SeqCst)).parse()) {
                        let _ = window.navigate(url);
                    }
                }
                refresh_tray(&app);
            }
        }
    }
}

// --- Preferences window (local page, the only one with IPC) ---------------------------------------

fn open_prefs(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("prefs") {
        let _ = window.set_focus();
        return;
    }
    if let Ok(window) = WebviewWindowBuilder::new(app, "prefs", WebviewUrl::App("prefs.html".into()))
        .title("Preferencias de Finnip")
        .inner_size(460.0, 300.0)
        .resizable(false)
        .center()
        .build()
    {
        let _ = window.set_focus();
    }
}

/// The overlay page says where the open 3D part is, or None once it closes.
#[tauri::command]
fn part_box(state: tauri::State<Finnip>, rect: Option<[f64; 4]>) {
    *state.part_box.lock().unwrap() = rect.filter(|r| r.iter().all(|v| v.is_finite()) && r[2] > 0.0 && r[3] > 0.0);
}

/// The overlay page asks for a project action on behalf of the server ("Finnip, nuevo proyecto…").
/// projects.rs checks every name, repository and command; a finished Claude Code task comes back to
/// the page through its hook, and the page passes it to the server.
#[tauri::command]
async fn project(app: AppHandle, mut request: projects::Request) -> Result<serde_json::Value, String> {
    // "Haz esto más grande": what the user points at, captured here (the page never names a file).
    if request.action == "capture" || (request.action == "task" && request.point) {
        let shot = tauri::async_runtime::spawn_blocking({
            let app = app.clone();
            move || capture_pointer(&app)
        })
        .await
        .map_err(|e| e.to_string())??;
        if request.action == "capture" {
            // For a project in the cloud: the server takes it to the runner.
            let jpeg = std::fs::read(&shot.file).map_err(|e| e.to_string())?;
            let _ = std::fs::remove_file(&shot.file);
            return Ok(serde_json::json!({ "jpeg": base64(&jpeg), "x": shot.x, "y": shot.y }));
        }
        request.shot = Some(shot);
    }
    let projects = app.state::<Arc<projects::Projects>>().inner().clone();
    let handle = app.clone();
    let on_done: projects::OnDone =
        Arc::new(move |done| page(&handle, &format!("window.finnipDesktop?.projectDone({done})")));
    tauri::async_runtime::spawn_blocking(move || projects.handle(request, on_done)).await.map_err(|e| e.to_string())?
}

/// The screen around the mouse pointer (pointer drawn in), with Finnip's overlay hidden for the moment.
/// Needs macOS's Screen Recording permission for Finnip (asked the first time).
fn capture_pointer(app: &AppHandle) -> Result<projects::Shot, String> {
    const W: f64 = 1400.0; // region in points, clamped to the monitor
    const H: f64 = 900.0;
    let cursor = app.cursor_position().map_err(|e| e.to_string())?;
    let monitor = app
        .monitor_from_point(cursor.x, cursor.y)
        .ok()
        .flatten()
        .or_else(|| app.primary_monitor().ok().flatten())
        .ok_or("No encontré la pantalla del puntero")?;
    let scale = monitor.scale_factor();
    let origin = monitor.position().to_logical::<f64>(scale);
    let size = monitor.size().to_logical::<f64>(scale);
    let (cx, cy) = (cursor.x / scale, cursor.y / scale);
    let (w, h) = (W.min(size.width), H.min(size.height));
    let x = (cx - w / 2.0).clamp(origin.x, origin.x + size.width - w);
    let y = (cy - h / 2.0).clamp(origin.y, origin.y + size.height - h);
    let file = std::env::temp_dir().join(format!(
        "pointer-{}.jpg",
        std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map_or(0, |d| d.as_millis())
    ));
    page(app, "window.finnipDesktop?.visible(false)");
    thread::sleep(Duration::from_millis(250)); // the overlay's fade
    let status = std::process::Command::new("/usr/sbin/screencapture")
        .args(["-x", "-C", "-t", "jpg", "-R", &format!("{x:.0},{y:.0},{w:.0},{h:.0}")])
        .arg(&file)
        .status();
    let shown = app.state::<Finnip>().visible.load(Ordering::SeqCst);
    page(app, &format!("window.finnipDesktop?.visible({shown})"));
    if !status.map_err(|e| e.to_string())?.success() || !file.exists() {
        return Err("No pude tomar la captura: dale permiso de Grabación de pantalla a Finnip".into());
    }
    let pct = |v: f64, from: f64, len: f64| (((v - from) / len) * 100.0).round().clamp(0.0, 100.0) as u32;
    Ok(projects::Shot { file, x: pct(cx, x, w), y: pct(cy, y, h) })
}

/// Standard base64, for the capture sent to the server.
fn base64(data: &[u8]) -> String {
    const ABC: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::with_capacity(data.len().div_ceil(3) * 4);
    for chunk in data.chunks(3) {
        let n = chunk.iter().enumerate().fold(0u32, |n, (i, b)| n | (u32::from(*b) << (16 - 8 * i)));
        for i in 0..4 {
            out.push(if i <= chunk.len() { ABC[(n >> (18 - 6 * i)) as usize & 63] as char } else { '=' });
        }
    }
    out
}

/// Whether a cursor at (x, y), in the overlay's CSS pixels, is over the part's box.
fn over_part(rect: Option<[f64; 4]>, x: f64, y: f64) -> bool {
    rect.is_some_and(|[left, top, width, height]| x >= left && x <= left + width && y >= top && y <= top + height)
}

/// While a 3D part is open, the overlay takes the mouse only with the cursor over the part's box, so it
/// can be turned and zoomed; everywhere else clicks keep going to the apps underneath.
fn follow_cursor(app: AppHandle) {
    let mut capturing = false;
    loop {
        let rect = *app.state::<Finnip>().part_box.lock().unwrap();
        let over = match (rect, overlay(&app)) {
            (Some(_), Some(window)) => match (app.cursor_position(), window.outer_position(), window.scale_factor()) {
                (Ok(cursor), Ok(origin), Ok(scale)) => over_part(
                    rect,
                    (cursor.x - f64::from(origin.x)) / scale,
                    (cursor.y - f64::from(origin.y)) / scale,
                ),
                _ => false,
            },
            _ => false,
        };
        if over != capturing {
            capturing = over;
            if let Some(window) = overlay(&app) {
                let _ = window.set_ignore_cursor_events(!over);
            }
        }
        thread::sleep(if rect.is_some() { CURSOR_EVERY } else { CURSOR_IDLE });
    }
}

#[tauri::command]
fn get_settings(state: tauri::State<Finnip>) -> Settings {
    state.settings.lock().unwrap().clone()
}

/// Registers the new shortcut before dropping the old one: if it cannot be used, the old one stays.
#[tauri::command]
fn set_shortcut(app: AppHandle, state: tauri::State<Finnip>, shortcut: String) -> Result<String, String> {
    if !valid_shortcut(&shortcut) {
        return Err("Incluye al menos ⌘, ⌥, ⌃ o ⇧ y una tecla.".into());
    }
    let old = state.settings.lock().unwrap().shortcut.clone();
    if shortcut == old {
        return Ok(shortcut);
    }
    let shortcuts = app.global_shortcut();
    shortcuts
        .register(shortcut.as_str())
        .map_err(|e| format!("No se pudo usar ese atajo (¿lo usa otra app?): {e}"))?;
    let _ = shortcuts.unregister(old.as_str());
    let mut settings = state.settings.lock().unwrap();
    settings.shortcut = shortcut.clone();
    save_settings(&state.path, &settings).map_err(|e| e.to_string())?;
    Ok(shortcut)
}

// --- app -------------------------------------------------------------------------------------------

fn main() {
    tauri::Builder::default()
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(|app, _shortcut, event| {
                    if event.state() == ShortcutState::Pressed {
                        talk(app);
                    }
                })
                .build(),
        )
        .plugin(tauri_plugin_autostart::init(MacosLauncher::LaunchAgent, None))
        .invoke_handler(tauri::generate_handler![get_settings, set_shortcut, part_box, project])
        .setup(|app| {
            #[cfg(target_os = "macos")]
            app.set_activation_policy(tauri::ActivationPolicy::Accessory); // no Dock icon, no Cmd-Tab

            let path = app.path().app_data_dir()?.join("settings.json");
            let first_run = !path.exists();
            let settings = load_settings(&path);
            if first_run {
                let _ = save_settings(&path, &settings);
                let _ = app.autolaunch().enable(); // starts with the session by default; the menu turns it off
            } else if app.autolaunch().is_enabled().unwrap_or(false) {
                let _ = app.autolaunch().enable(); // rewrite the login item with this copy's path (moved to /Applications)
            }
            if let Err(e) = app.global_shortcut().register(settings.shortcut.as_str()) {
                eprintln!("atajo {} no disponible: {e}", settings.shortcut);
            }
            let muted = settings.muted;
            let home = PathBuf::from(std::env::var("HOME").unwrap_or_else(|_| "/tmp".into()));
            let data = app.path().app_data_dir()?;
            app.manage(Arc::new(projects::Projects::new(home, data.join("projects.json"))));
            app.manage(Finnip {
                path,
                settings: Mutex::new(settings),
                muted: AtomicBool::new(muted),
                visible: AtomicBool::new(true),
                online: AtomicBool::new(true),
                shown_on: Mutex::new(None),
                part_box: Mutex::new(None),
            });
            // The overlay page (and only it, at FINNIP_URL) may call part_box.
            app.add_capability(
                CapabilityBuilder::new("overlay-part")
                    .remote(format!("{}/*", FINNIP_URL.trim_end_matches('/')))
                    .window("overlay")
                    .permission("allow-part-box")
                    .permission("allow-project"),
            )?;

            let overlay = WebviewWindowBuilder::new(app, "overlay", WebviewUrl::External(page_url(muted).parse()?))
                .title("Finnip")
                .transparent(true)
                .decorations(false)
                .shadow(false)
                .always_on_top(true)
                .visible_on_all_workspaces(true)
                .skip_taskbar(true)
                .focused(false)
                .resizable(false)
                .build()?;
            overlay.set_ignore_cursor_events(true)?; // clicks and keys go to the apps underneath
            let handle = app.handle().clone();
            place_overlay(&handle);

            TrayIconBuilder::with_id(TRAY)
                .icon(tray_icon(&handle))
                .icon_as_template(true)
                .tooltip("Finnip")
                .menu(&build_menu(&handle)?)
                .show_menu_on_left_click(true)
                .on_menu_event(|app, event| on_menu(app, event.id().as_ref()))
                .build(app)?;

            let cursor = handle.clone();
            thread::spawn(move || watch(handle));
            thread::spawn(move || follow_cursor(cursor));
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("Finnip no pudo arrancar");
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_path(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("finnip-desktop-test-{name}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        dir.join("settings.json")
    }

    #[test]
    fn missing_or_damaged_settings_fall_back_to_defaults() {
        let path = temp_path("damaged");
        assert_eq!(load_settings(&path), Settings::default());
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(&path, "{ esto no es json").unwrap();
        assert_eq!(load_settings(&path), Settings::default());
        fs::write(&path, r#"{"display": "HUAWEI AD80HW@0,0"}"#).unwrap(); // file without shortcut
        assert_eq!(load_settings(&path).shortcut, DEFAULT_SHORTCUT);
    }

    #[test]
    fn settings_round_trip() {
        let path = temp_path("roundtrip");
        let settings = Settings { display: Some("HUAWEI AD80HW@1920,0".into()), shortcut: "Control+Alt+Space".into(), muted: true };
        save_settings(&path, &settings).unwrap();
        assert_eq!(load_settings(&path), settings);
        assert!(!path.with_extension("json.tmp").exists());
    }

    #[test]
    fn the_mouse_is_taken_only_over_the_part() {
        let rect = Some([100.0, 50.0, 400.0, 400.0]);
        assert!(over_part(rect, 300.0, 250.0));
        assert!(over_part(rect, 100.0, 450.0)); // on the edge
        assert!(!over_part(rect, 99.0, 250.0));
        assert!(!over_part(rect, 300.0, 451.0));
        assert!(!over_part(None, 300.0, 250.0)); // no part open
    }

    #[test]
    fn base64_matches_the_standard() {
        assert_eq!(base64(b""), "");
        assert_eq!(base64(b"f"), "Zg==");
        assert_eq!(base64(b"fo"), "Zm8=");
        assert_eq!(base64(b"foo"), "Zm9v");
        assert_eq!(base64(b"foobar\xff"), "Zm9vYmFy/w==");
    }

    #[test]
    fn shortcuts_need_a_modifier_and_one_key() {
        assert!(valid_shortcut("Alt+Super+F"));
        assert!(valid_shortcut("Control+Alt+Space"));
        assert!(!valid_shortcut("F"));
        assert!(!valid_shortcut("Super+Alt"));
        assert!(!valid_shortcut("Hyper+F"));
        assert!(!valid_shortcut("Alt+"));
    }
}
