# Design

## Decisions
- **Captura con `screencapture`.** Se usa `screencapture -x -C -t jpg -R x,y,w,h` del sistema: sin dependencias, con el puntero dibujado (`-C`). La región se calcula con la posición del cursor en puntos (Tauri `cursor_position` entre el `scale_factor` del monitor) y se ajusta para no salirse del monitor.
- **La página nunca nombra archivos.** `Request.shot` se marca con `serde(skip)` y solo lo llena `main.rs`. La acción `capture` solo la puede pedir el propio gateway, no Hermes.
- **La imagen la ve Claude Code**, no el modelo de Finnip: la abre con Read desde el proyecto, así que funciona con cualquier modelo de conversación.
- **Nube:** la captura viaja en base64 por el WebSocket (JPEG de unos cientos de KB). El servicio revisa que sea un JPEG de hasta 8 MB.
