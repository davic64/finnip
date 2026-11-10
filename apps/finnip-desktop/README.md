# Finnip para macOS

App de escritorio (Tauri v2) que pone a Finnip como una capa transparente sobre la pantalla:

- Invisible en reposo.
- Holograma en la esquina cuando lo despiertas con «Finnip» o cuando da un aviso.
- Al centro, con el fondo oscurecido, para el estado del servidor y la agenda.
- Aviso pasajero cuando cambia la canción.

No hay que reescribir la interfaz: la app carga la misma página que sirve el voice gateway, en modo escritorio (`?desktop=1`). Los clics y el teclado siempre pasan a las apps de debajo.

## Requisitos (en la Mac)

- macOS 13 o posterior.
- Rust: `brew install rustup && rustup-init`. Comprueba con `rustc --version`.
- Command Line Tools de Xcode: `xcode-select --install`. Comprueba con `xcode-select -p`.
- Node.js 20 o posterior.
- La Mac en la tailnet de Finnip. La app se identifica con tu usuario de Tailscale, a través de Caddy.

## Compilar e instalar

`FINNIP_URL` es la dirección HTTPS del gateway en tu tailnet. Se fija al compilar y no se guarda en el repo.

```bash
cd apps/finnip-desktop
npm install
FINNIP_URL=https://finnip.<tu-tailnet>.ts.net npx tauri build --bundles app
cp -R src-tauri/target/release/bundle/macos/Finnip.app /Applications/
open /Applications/Finnip.app
```

La primera vez:

1. **Gatekeeper.** La app no está firmada. Si macOS no la abre, ve a Ajustes del Sistema → Privacidad y seguridad → «Abrir de todos modos».
2. **Micrófono.** Acepta el permiso. Si lo negaste, actívalo en Ajustes del Sistema → Privacidad y seguridad → Micrófono → Finnip.
3. **Inicio con la sesión.** Queda activado. Se desactiva en el menú del ícono, con «Abrir al iniciar sesión».

Para desarrollo hay un bundle de depuración más rápido de compilar: `npx tauri build --debug --bundles app`. Queda en `src-tauri/target/debug/bundle/macos/`.

## Uso

- **Ícono en la barra superior.** Muestra el estado (escuchando, silenciado, sin conexión) y permite:
  - Mostrar u ocultar a Finnip.
  - Silenciar el micrófono.
  - Elegir la **pantalla**. Los monitores con el mismo nombre aparecen como «· 1», «· 2», de izquierda a derecha.
  - Abrir **Preferencias** (⌘,).
  - Activar o desactivar el inicio con la sesión.
  - Salir.
- **Atajo global**, ⌥⌘F por defecto. Te deja hablar sin decir «Finnip». Si lo presionas otra vez antes de hablar, Finnip vuelve a reposo. Se cambia en Preferencias → «Cambiar». No uses un atajo que tus apps ya ocupen, como ⌘F para buscar: el atajo global se lo quitaría a todas las apps.
- **Una sola interfaz con micrófono a la vez.** Si tienes la app abierta, no dejes también la interfaz web escuchando en el navegador.

Las preferencias (pantalla y atajo) están en `~/Library/Application Support/dev.finnip.desktop/settings.json`.

## Seguridad

- La página que carga la app viene del gateway y **no tiene acceso a ninguna API nativa**. La app solo le habla en un sentido (`window.finnipDesktop`), y Tauri rechaza cualquier comando que la página intente. Se verificó con `set_shortcut`.
- Solo la ventana local de Preferencias puede leer los ajustes y cambiar el atajo (`src-tauri/capabilities/prefs.json`).

## Pruebas

```bash
cargo test --manifest-path src-tauri/Cargo.toml   # preferencias y validación del atajo
```

El modo escritorio de la interfaz se prueba en `apps/finnip-app` con `npm test`.

## Desinstalar

1. En el menú del ícono, desactiva «Abrir al iniciar sesión» y luego elige «Salir de Finnip».
2. Borra los archivos:

```bash
rm -rf /Applications/Finnip.app ~/Library/Application\ Support/dev.finnip.desktop
rm -f ~/Library/LaunchAgents/Finnip.plist
```
