# Design

## Context
- La app web (`apps/finnip-app`) ya tiene una vista de pantalla completa para navegador, y el modo `?desktop=1` para el overlay de macOS.
- El voice gateway acepta varias conexiones a la vez:
  - Si dos dispositivos oyen la misma frase, solo una llega a Hermes.
  - Cada respuesta suena en el dispositivo que la envió.
  - Las piezas y las fotos solo van a la app de escritorio (`hello` con `client: "desktop"`).
- Caddy sirve todo con HTTPS en la tailnet, así que el celular necesita Tailscale.
- El micrófono del WebView solo funciona en un origen seguro (HTTPS) y con el permiso `RECORD_AUDIO` concedido por la app.
- El celular es un Redmi Note 9 con MIUI y Android 10–12.

## Goals / Non-Goals
**Goals:**
- Un APK que se instala una vez y queda como un Echo con pantalla, sin tocarlo.
- La Mac decide si escucha; la pantalla de la Mac sigue mostrando lo que se pide desde el celular.

**Non-Goals:**
- Una app Android nativa con su propia interfaz: la interfaz sigue siendo la app web.
- Escuchar con la pantalla apagada o la app en segundo plano: la pantalla nunca se apaga.

## Decisions
- **WebView en Java, sin Kotlin ni Tauri.**
  - Tauri para Android necesita NDK y compilar Rust para Android.
  - Una TWA (Chrome) no puede cambiar el brillo de la ventana.
  - Java solo necesita el SDK y Gradle, y la app es una sola actividad.
- **URL en tiempo de compilación** (`-PfinnipUrl=` o `FINNIP_URL`), como la app de escritorio, para que el nombre de la tailnet no quede en el repo público.
- **Brillo con `WindowManager.LayoutParams.screenBrightness`.** Solo cambia el brillo de esta ventana, no el del sistema, y no necesita el permiso `WRITE_SETTINGS`. La página llama a `FinnipPhone.dim(true|false)` desde un `JavascriptInterface`. Se atenúa tras 10 s en reposo.
- **Permisos limitados al origen de Finnip.** `onPermissionRequest` solo concede `AUDIO_CAPTURE` si la página es la de `FINNIP_URL`.
- **Kiosco como launcher.** La actividad declara la categoría `HOME`:
  - Si el usuario la elige como inicio, arranca al encender el teléfono sin un `BOOT_COMPLETED`, que Android 10+ limita.
  - El botón atrás no sale de la app.
- **Paneles a la Mac en el gateway.** `Session.show_panel` manda `stats` y `reminders` a las apps de escritorio si la sesión no es de escritorio y hay al menos una. Si no hay, los muestra en el mismo dispositivo.
- **Escucha de la Mac.**
  - `Settings.muted` se guarda en `settings.json`.
  - La URL del overlay lleva `&muted=1` para que la página no abra el micrófono al cargar.
  - Al cambiar la opción, la página actualiza su URL con `history.replaceState` para que una recarga respete el estado.
  - Con la escucha desactivada, el atajo abre el micrófono. Cuando Finnip vuelve al reposo, la página lo cierra.

## Risks / Trade-offs
- Si la Mac escucha a la vez que el celular, responde el dispositivo que mandó primero la frase. → Desactivar la escucha en la Mac cuando el celular está al lado.
- La batería se puede inflar con el cargador puesto 24/7. → Fuera de alcance; un enchufe inteligente lo resuelve después.
- MIUI mata apps en segundo plano. → La app está siempre al frente como launcher. Si hace falta, desactivar el ahorro de batería para Finnip.
