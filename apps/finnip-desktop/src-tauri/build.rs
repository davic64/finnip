fn main() {
    // The app's own commands go through the capability system, so only windows granted them can call
    // them: capabilities/prefs.json (the local Preferences window) and, for part_box only, the overlay
    // page at FINNIP_URL (granted at startup in main.rs, so the tailnet name stays out of the repo).
    tauri_build::try_build(
        tauri_build::Attributes::new()
            .app_manifest(tauri_build::AppManifest::new().commands(&["get_settings", "set_shortcut", "part_box", "project"])),
    )
    .expect("tauri build");
}
