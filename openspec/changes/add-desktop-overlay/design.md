# Design

## Context

- La interfaz (`apps/finnip-app`, Vite, TypeScript y Three.js) la sirve el voice gateway detrás de Caddy, en el nombre HTTPS de la tailnet. `link.ts` abre el WebSocket con `location.host`, así que la misma página funciona en cualquier origen donde se cargue.
- La identidad del usuario la pone Caddy (`tailscale_auth` → `Tailscale-User-Login`). La Mac del usuario está en la tailnet, así que una app que cargue esa URL queda autenticada sin hacer nada más.
- El gateway ya emite todo lo que necesitan las escenas: los estados de la conversación, `stats`, `reminders`, `now_playing`, `device`, `announce` y `wake`. También ya aplica el reposo con "Finnip" y las ventanas de 4 s mientras suena música.
- `holo.ts` limita los fps, pero nunca deja de dibujar. El usuario ya se quejó del consumo en su Mac.

## Goals / Non-Goals

**Goals:**
- Una app ligera que muestre la interfaz existente como overlay, con escenas pensadas para el escritorio.
- Cero cambios en el servidor.
- Que el contenido remoto no gane ningún poder sobre la Mac.

**Non-Goals:**
- Controlar la computadora.
- Wake word local.
- Cámara.
- Overlay sobre apps en pantalla completa nativa.
- Finnip en varias pantallas a la vez (se elige una).
- Firmar o notarizar la app.

## Decisions

### Tauri v2 cargando la URL del gateway
La app es un cascarón Tauri cuya única ventana carga `https://<tailnet>/?desktop=1`. La URL se fija al compilar con la variable `FINNIP_URL`, así el nombre de la tailnet no se versiona en el repo.
- *Alternativa: empaquetar la interfaz dentro de la app.* Habría que recompilar en cada cambio y apuntar el WebSocket a otro host. Se descarta.
- *Alternativa: Electron.* Es más fácil para overlays, pero cuesta unos 150 MB o más de RAM y trae su propio Chromium. El consumo en la Mac importa, así que se descarta.

### El overlay siempre deja pasar los clics
La ventana se configura así: `transparent`, sin decoraciones ni sombra, `alwaysOnTop`, `visibleOnAllWorkspaces`, `skipTaskbar`, sin foco al abrir, posición y tamaño de la pantalla elegida, y `set_ignore_cursor_events(true)` permanente. La app usa la política de activación *Accessory*, así que no aparece en el Dock ni en Cmd-Tab. La transparencia en macOS requiere `macOSPrivateApi`, lo cual es aceptable porque la app no va a la App Store.
- Toda la interacción pasa por la barra de menú y el atajo global. No hay zonas clicables, lo que evita tener que detectar en qué píxel hay contenido.

### Ninguna API nativa para la página
No se declaran capabilities de Tauri para orígenes remotos, así que la página no tiene IPC. La parte nativa habla con la página en una sola dirección: `webview.eval()` llama a un gancho pequeño que la página expone, `window.finnipDesktop`, con `talk()`, `mute(bool)` y `visible(bool)`.
- Para saber si hay conexión y mostrarlo en el ícono, la parte nativa consulta `GET /health` del gateway cada 10 s, sin preguntarle a la página.
- Con esto, aunque la página remota se comprometa, no puede tocar la Mac.

### Escenas en la interfaz web, no en la parte nativa
Un módulo nuevo, `desktop.ts`, se activa con `?desktop=1`. Calcula la escena (`hidden`, `corner` o `center`) a partir del estado de la conversación y de los eventos, y la pone en `body.dataset.scene`. CSS bajo `body.desktop` mueve el holograma, la capa oscura y los paneles existentes (`Hud`, `showAgenda`, `showNowPlaying`, `showCard`), con transiciones de opacidad y transformaciones.
- La decisión de escena es una función pura, `sceneFor(...)`, probada con `node --test` como ya se hace con `player.test.mjs`.
- En modo escritorio: fondo transparente; no se muestra el orbe ni la barra de estado; el micrófono se abre en modo conversación y arranca en reposo; `now_playing` se muestra solo al cambiar de canción y se oculta solo.

### `holo.ts` se pausa de verdad
Se agrega `holo.paused`. Cuando la escena es `hidden`, el bucle de `requestAnimationFrame` se detiene, y al cambiar a otra escena se reanuda. Así, en reposo la app no dibuja nada.

### Barra de menú, atajo y arranque
- La barra de menú usa el `tray-icon` de Tauri. Sus íconos indican escuchando, silenciado o sin conexión.
- El atajo global se registra con `tauri-plugin-global-shortcut` (⌥⌘F por defecto) y llama a `finnipDesktop.talk()`.
- El inicio con la sesión usa `tauri-plugin-autostart` (LaunchAgent).

### Preferencias guardadas en un JSON local
`settings.json` en el directorio de datos de la app (`~/Library/Application Support/<id>/`) guarda `{"display": <nombre de la pantalla>, "shortcut": "Alt+Super+F"}`. Lo lee y lo escribe solo la parte nativa.
- *Alternativa: `tauri-plugin-store`.* Es una dependencia más para dos valores. Se descarta.

### Pantalla elegida desde la barra de menú
- El submenú "Pantalla" se arma con `available_monitors()`, con un ítem de selección por monitor y la principal marcada como predeterminada.
- Al elegir una, la ventana se mueve y se redimensiona a ese monitor (`set_position` y `set_size` con sus coordenadas lógicas) y se guarda el nombre.
- Un vigilante cada 5 s compara la lista de monitores: si el guardado no está, usa el principal; cuando vuelve, regresa a él. Al hacerlo, rehace el submenú.
- Se identifica por nombre porque es lo que expone Tauri. Dos monitores idénticos pueden compartir nombre; en ese caso se usa el primero que coincida, y esto queda como limitación aceptada.
- No hace falta una ventana: es una elección de una lista.

### Ventana de Preferencias para el atajo
- El overlay no recibe teclado, así que el atajo se graba en una ventana normal y pequeña, "Preferencias", abierta desde el menú.
- Su contenido es **HTML local empaquetado en la app**, no la página del gateway. Es el único origen con capability de IPC, limitada a dos comandos propios: `get_settings` y `set_shortcut`.
- `set_shortcut` valida que la combinación tenga al menos un modificador e intenta registrarla **antes** de soltar la anterior. Si falla, devuelve el error y conserva la anterior. Si funciona, quita la anterior y guarda la nueva.
- Incluye "Restablecer" para volver a ⌥⌘F.
- *Alternativa: elegir de una lista fija de atajos en el menú.* Es más simple, pero no es personalizar de verdad. Se descarta.

## Risks / Trade-offs

- [El micrófono en WKWebView con una página remota puede no pedir permiso o no funcionar] → La primera tarea es una prueba: `getUserMedia` dentro de la ventana Tauri con `NSMicrophoneUsageDescription` en el Info.plist. Si falla, la parte nativa responde la solicitud de captura (WKUIDelegate) y concede el micrófono solo para el origen del gateway.
- [WKWebView bloquea el audio sin un gesto del usuario, y en el overlay no hay clics] → La misma prueba verifica que la voz suene. Si no, se configura `mediaTypesRequiringUserActionForPlayback = []` en la configuración de la vista desde Rust.
- [Que la ventana tome el foco al aparecer quitaría el teclado a la app activa] → Se abre sin foco y nunca se llama a `set_focus`. Esto se verifica a mano escribiendo en otra app mientras Finnip habla.
- [La interfaz web abierta en el navegador y la app escuchan a la vez] → Se documenta usar una sola. La coordinación de micrófonos queda fuera de este cambio.
- [Las apps en pantalla completa nativa tapan el overlay] → Es aceptable en esta fase (está en Non-Goals). Se puede subir el nivel de la ventana después.
- [Dibujar el holograma transparente sobre todo el escritorio cuesta GPU] → Se dibuja solo en las escenas visibles y con el tope de fps actual.
- [Pantallas con distinta escala (Retina y externa) pueden dejar el overlay mal dimensionado al moverlo] → Se usan coordenadas lógicas del monitor destino y se verifica a mano al cambiar entre la pantalla de la Mac y un monitor externo.
- [La ventana de Preferencias con IPC amplía lo que puede invocar código de la app] → La capability aplica solo a la etiqueta de esa ventana y a su origen local, y expone solo `get_settings` y `set_shortcut`. El overlay remoto sigue sin IPC.

## Migration Plan

1. Se despliega primero el modo escritorio de la interfaz. Es inofensivo: solo se activa con `?desktop=1`.
2. Se compila la app en la Mac con `FINNIP_URL=… npm run tauri build`, se copia a `/Applications` y se permite una vez en Gatekeeper.
3. **Vuelta atrás:** cerrar la app y desactivar el inicio con la sesión. La interfaz web sigue igual.
