fn main() {
    // The app's own commands go through the capability system, so only windows granted them
    // (capabilities/prefs.json: the local Preferences window) can call them.
    tauri_build::try_build(
        tauri_build::Attributes::new()
            .app_manifest(tauri_build::AppManifest::new().commands(&["get_settings", "set_shortcut"])),
    )
    .expect("tauri build");
}
