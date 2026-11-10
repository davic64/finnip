# Tasks

## 1. Prueba de concepto de la ventana Tauri

- [x] 1.1 Instalar en la Mac Rust (rustup) y las Command Line Tools de Xcode. Verificar que `rustc --version` y `xcode-select -p` respondan.
- [x] 1.2 Crear `apps/finnip-desktop/` con `npm create tauri-app` (Tauri v2), con una ventana que cargue `FINNIP_URL`, transparente, sin decoraciones ni sombra, siempre encima, en todos los Espacios, sin foco y con `set_ignore_cursor_events(true)`, más `macOSPrivateApi` y la política *Accessory*. Verificar con `npm run tauri dev`: la interfaz se ve sobre el escritorio, los clics y el teclado llegan a la app de debajo, y no aparece en el Dock ni en Cmd-Tab.
- [x] 1.3 Agregar `NSMicrophoneUsageDescription` al Info.plist y comprobar dentro de la app que `getUserMedia` funciona y que la voz de Finnip suena sin hacer clic. Si alguno falla, aplicar la mitigación de design.md (conceder el permiso para el origen del gateway y `mediaTypesRequiringUserActionForPlayback = []`) y verificar con "Finnip, ¿qué hora es?" de punta a punta.

## 2. Modo escritorio en la interfaz web

- [x] 2.1 Crear `apps/finnip-app/src/desktop.ts` con la función pura `sceneFor(...)`, que mapea estado y evento a `hidden`, `corner` o `center`, más la lógica de música (mostrar solo al cambiar de canción). Agregar `tests/desktop.test.mjs` con los escenarios de la spec (reposo, despertar, aviso, stats o agenda al centro, cambio de canción, pausa) y verificar con `npm test`.
- [x] 2.2 Activar el modo con `?desktop=1` en `main.ts`: `body.desktop`, fondo transparente, sin orbe ni barra de estado, micrófono abierto en modo conversación arrancando en reposo, `body.dataset.scene` según `sceneFor`, y el gancho `window.finnipDesktop` con `talk()`, `mute(bool)` y `visible(bool)`. Verificar con `npm run build` y abriendo `https://<tailnet>/?desktop=1` en el navegador: en reposo no se ve nada, y al decir "Finnip" el holograma aparece en la esquina.
- [x] 2.3 Agregar `paused` a `holo.ts` para que el bucle de animación se detenga en `hidden` y se reanude al mostrarse. Verificar en el Monitor de Actividad, o en el panel Performance del navegador, que en reposo no hay frames dibujados.
- [x] 2.4 Agregar los estilos de escena bajo `body.desktop` en `style.css`: holograma en la esquina, escena central con capa oscura semitransparente, aviso de música y tarjetas pasajeras, con transiciones de opacidad. Verificar a mano cada escena de la spec en `?desktop=1`: estado del servidor, agenda, cambio de canción, luz encendida y aviso de la impresora.
- [x] 2.5 Confirmar que la interfaz normal, sin `?desktop=1`, no cambia. Verificar con `npm test`, `npm run typecheck` y una conversación en la pestaña normal.

## 3. Controles nativos

- [x] 3.1 Agregar el ícono de barra de menú (`tray-icon`) con mostrar u ocultar, silenciar u oír el micrófono y salir. Silenciar llama a `finnipDesktop.mute(true)` con `webview.eval`. Verificar que silenciar oculta a Finnip y que ya no despierta con "Finnip".
- [x] 3.2 Agregar el estado de conexión: consultar `GET /health` cada 10 s y reflejarlo en el ícono. Verificar reiniciando el voice gateway: el ícono muestra "sin conexión" y vuelve solo.
- [x] 3.3 Agregar `settings.json` en el directorio de datos de la app (leer con valores por defecto si no existe o está dañado; escribir de forma atómica), con una prueba unitaria en Rust (`cargo test`) para lectura, valores por defecto y escritura.
- [x] 3.4 Agregar el atajo global (`tauri-plugin-global-shortcut`), leído de `settings.json` (por defecto ⌥⌘F), que llama a `finnipDesktop.talk()`. Verificar que, en reposo, el atajo hace aparecer el holograma escuchando y la frase se atiende sin decir "Finnip".
- [x] 3.5 Agregar el submenú "Pantalla", con un ítem de selección por monitor de `available_monitors()`. Al elegir uno, mover y redimensionar el overlay y guardar el nombre. Agregar el vigilante cada 5 s que cae a la principal y regresa al reconectar. Verificar con la pantalla de la Mac y un monitor externo: elegir, reiniciar la app (debe recordar la elección), desconectar y reconectar el monitor.
- [x] 3.6 Crear la ventana de Preferencias con HTML local empaquetado: muestra el atajo actual, tiene "Cambiar" (graba la siguiente combinación y rechaza las que no tengan modificador) y "Restablecer". Agregar los comandos `get_settings` y `set_shortcut`: registrar la nueva antes de soltar la anterior y, si falla, conservar la anterior. La capability aplica solo a esta ventana. Verificar los tres escenarios de "Atajo personalizable" de la spec, incluido elegir un atajo que ya use otra app.
- [x] 3.7 Agregar el inicio con la sesión (`tauri-plugin-autostart`) con una opción en el menú. Verificar cerrando y abriendo sesión: la app arranca en reposo, en la pantalla y con el atajo guardados.
- [x] 3.8 Revisar que el overlay remoto no tenga capabilities de Tauri. Verificar desde la consola de la página del overlay que `window.__TAURI__` y `__TAURI_INTERNALS__.invoke` no estén disponibles o no tengan efecto, y que `set_shortcut` no se pueda invocar desde ahí.

- [x] 3.9 Interrupción: mientras habla, el micrófono sigue abierto en la app y solo cuenta "Finnip, …" (barge-in con la wake word). "Finnip" solo o con "para", "cállate" o "basta" lo calla sin ir a Hermes; con otra petición, corta y atiende. El atajo lo calla. Su propia voz se descarta como eco. Verificado con pruebas del gateway (`test_finnip_para_stops_the_reply_without_asking_hermes`, `test_own_voice_saying_finnip_does_not_interrupt`, `StopTest`).

## 4. Empaquetado y documentación

- [x] 4.1 Escribir `apps/finnip-desktop/README.md` con requisitos, `FINNIP_URL=… npm run tauri build`, instalación en `/Applications`, permitirla en Gatekeeper, permisos y desinstalación. Verificar siguiendo el README desde cero en la Mac.
- [x] 4.2 Agregar a `.gitignore` `apps/finnip-desktop/src-tauri/target/` y los binarios generados. Verificar con `git status` limpio después de compilar.

## 5. Verificación integral

- [x] 5.1 Con la app instalada, recorrer todos los escenarios de `specs/desktop-overlay/spec.md`: escribir en otra app mientras Finnip habla, cambiar de Espacio, música sin "Finnip", aviso de la impresora, que el reposo no consuma GPU, cambiar de pantalla y de atajo, y que ambos se conserven después de reiniciar la Mac. Anotar el resultado de cada escenario en el PR.

## Workflow follow-up

- Abrir un PR con el cambio. El usuario hace el merge.
- Archivar el cambio en OpenSpec después del merge y revisar la spec resultante en `openspec/specs/desktop-overlay/`.
