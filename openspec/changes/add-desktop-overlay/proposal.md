# Proposal

## Why

Hoy Finnip vive en una pestaña del navegador: hay que abrirla, ocupa una ventana y no se integra con lo que el usuario está haciendo en su Mac. El siguiente paso es que Finnip esté siempre presente en el escritorio de forma inmersiva: invisible en reposo y apareciendo como holograma flotante, paneles y avisos sobre lo que haya en pantalla cuando se le habla o tiene algo que decir.

## What Changes

- Nueva app de escritorio para macOS, `apps/finnip-desktop/`, hecha con Tauri v2. Es una ventana overlay transparente, sin bordes, siempre encima y que deja pasar todos los clics, sobre la pantalla que elija el usuario (por defecto la principal).
- La app carga la misma interfaz web que ya sirve el voice gateway (`https://<nombre-tailnet>/?desktop=1`) en vez de duplicarla. Las mejoras de la interfaz llegan sin recompilar la app.
- Nuevo modo escritorio en `apps/finnip-app`. Cuando la página corre dentro de la app, convierte los eventos que ya existen en escenas:
  - **Reposo:** nada visible y sin dibujar.
  - **Al despertarla o cuando habla:** holograma flotante en una esquina.
  - **Estado del servidor y agenda:** holograma al centro y fondo oscurecido.
  - **Música:** aviso de "reproduciendo" con el volumen, que aparece al cambiar de canción y se desvanece.
  - **Dispositivos y avisos de la impresora:** tarjetas breves.
- En la app, el micrófono queda siempre abierto en modo conversación con reposo: despierta con "Finnip", igual que la interfaz web actual.
- Ícono en la barra de menú (mostrar u ocultar Finnip, silenciar el micrófono, elegir la pantalla, preferencias, salir), atajo de teclado global para hablar o silenciar, e inicio automático con la sesión.
- Pantalla elegible desde la barra de menú, entre las conectadas. Si esa pantalla se desconecta, Finnip pasa a la principal y regresa sola cuando se reconecta.
- Ventana de Preferencias para personalizar el atajo grabando la combinación de teclas. La elección de pantalla y el atajo se guardan entre reinicios.
- La página remota no tiene acceso a ninguna API nativa de Tauri: la app solo la muestra.
- Sin cambios en el voice gateway, Hermes, Home Bridge ni `compose.yaml`.
- **Fuera de alcance:** controlar la computadora (abrir apps, teclado, ratón), wake word local, cámara, firma y notarización con Apple, Windows y Linux.

## Capabilities

### New Capabilities

- `desktop-overlay`: presencia de Finnip en el escritorio de macOS. Cubre la ventana overlay (transparente, siempre encima, sin capturar clics), las escenas que muestra según los eventos del gateway, el micrófono en reposo con wake word, los controles de la barra de menú, el atajo global y el inicio con la sesión, y las preferencias del usuario (pantalla y atajo).

### Modified Capabilities

## Impact

- **Código nuevo:** `apps/finnip-desktop/`, con la app Tauri (Rust y `tauri.conf.json`), el ícono de la barra de menú, la ventana de Preferencias (HTML local empaquetado en la app) y su README de compilación.
- **Datos locales:** un archivo de preferencias en `~/Library/Application Support/` de la app.
- **Código modificado:** `apps/finnip-app/src/`:
  - Nuevo módulo de escenas del modo escritorio.
  - `main.ts` lo activa con `?desktop=1`.
  - `holo.ts` deja de dibujar cuando está oculto.
  - Estilos del overlay.
- **Dependencias nuevas** solo en la app de escritorio: Tauri v2 y sus plugins `global-shortcut` y `autostart`. En la Mac hacen falta Rust y las Command Line Tools de Xcode para compilar.
- **Compilación:** la app se compila en la Mac del usuario (macOS), no en el servidor ni en Docker. CI solo revisa el modo escritorio de la interfaz web.
- **Permisos de macOS:** micrófono, la primera vez.
- **Sin cambios** en APIs del gateway, despliegue del servidor ni secretos.
