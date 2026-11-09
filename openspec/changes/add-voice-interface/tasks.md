# Tasks

## 1. Verificación previa

- [x] 1.1 Desde un contenedor temporal en `compose_default`, con `API_SERVER_HOST=0.0.0.0` aplicado en una prueba aprobada, verificar `POST /v1/responses` con `stream: true` y `conversation: "finnip-voice"`. Medir el tiempo al primer token y confirmar el formato de los eventos SSE.
- [x] 1.2 Revisar si el API server permite marcar una petición como turno de voz (`auxiliary.voice_chat`). Anotar el resultado en design.md.
- [x] 1.3 Confirmar que el hook `pre_llm_call` de `finnip-lights` se ejecuta en peticiones del API server.
- [x] 1.4 Verificar cómo cancelar un turno en curso del API server (cerrar el SSE o `/v1/runs/{id}/stop`). Revisar si se puede reemplazar la respuesta guardada por la parte oída y anotar en design.md cuál de las dos opciones de la decisión 9 se usa.

## 2. `voice-gateway` (backend)

- [x] 2.1 Crear `apps/voice-gateway/` (Starlette + uvicorn) con `GET /health`, archivos estáticos de la PWA y el WebSocket `/ws` con `hello`.
- [x] 2.2 Implementar el control de acceso: exigir `Tailscale-User-Login` presente y dentro de `ALLOWED_TAILSCALE_USERS`. Rechazar con 403 en caso contrario.
- [x] 2.3 Implementar la recepción de PCM16 y `utterance_end`, y transcribir con faster-whisper `base` (CPU/int8, `language: es`, `vad_filter`, `initial_prompt`).
- [x] 2.4 Implementar el cliente de Hermes: `/v1/responses` en streaming con `conversation: "finnip-voice"` y cancelación.
- [x] 2.5 Implementar el corte en frases y Edge TTS por frase, en paralelo con el stream, enviando el audio en orden con `seq`.
- [x] 2.6 Implementar `cancel`, `done` y `error`, con mensajes sin datos sensibles.
- [x] 2.7 Implementar `interrupt`: cancelar Hermes y la síntesis, armar el texto oído a partir de `played_seq`/`played_ms`, aplicarlo al siguiente turno, y descartar como eco (con `resume`) la frase que se parezca a lo que Finnip estaba diciendo.
- [x] 2.8 Escribir tests `unittest`: protocolo, acceso, corte en frases, orden de los fragmentos, cancelación, interrupción (texto oído y nota del siguiente turno) y descarte de eco, con STT, Hermes y TTS simulados.
- [x] 2.9 Escribir el script `apps/voice-gateway/tools/ws_client.py`, que envía un WAV por `/ws` y mide la latencia al primer audio. Sirve de cliente de referencia para el ESP32.

## 3. PWA etapa A (funcional)

- [x] 3.1 Crear `apps/finnip-app/` (Vite + TypeScript) con `manifest.webmanifest`, service worker e íconos, que pueda instalarse en iOS y macOS.
- [x] 3.2 Implementar la captura con `getUserMedia` (`echoCancellation: true`), el VAD con `@ricky0123/vad-web` y el envío de PCM16 de 16 kHz por `/ws`.
- [x] 3.3 Implementar el modo conversación: un botón que activa y desactiva, con el cierre de todas las pistas al desactivar.
- [x] 3.4 Implementar el modo un mensaje: se cierra solo tras el primer `utterance_end`.
- [x] 3.5 Implementar la reproducción en cola con la Web Audio API, con corte inmediato y vaciado de la cola.
- [x] 3.6 Implementar la interrupción con un toque (en ambos modos) y con la voz (modo conversación: umbral más alto y unos 300 ms de voz mientras Finnip habla), enviando `interrupt` con `played_seq`/`played_ms`. Agregar el ajuste "Interrumpir con la voz" y manejar `resume`.
- [x] 3.7 Mostrar el estado (apagado, escuchando, pensando, hablando), la transcripción, el texto de la respuesta y las métricas de latencia en modo debug.

## 4. Integración y despliegue (requiere aprobación explícita)

- [x] 4.1 Agregar el servicio `voice-gateway` a `compose/compose.yaml` (puerto solo en `127.0.0.1`) y `API_SERVER_HOST=0.0.0.0` a `hermes`. Crear `config/voice-gateway.env`.
- [x] 4.2 Configurar `tailscale serve` hacia `voice-gateway` y verificar HTTPS en `*.ts.net`.
- [x] 4.3 Agregar el job `voice-gateway` a `.github/workflows/ci.yml` y documentar la arquitectura, el despliegue y la instalación de la PWA en `README.md`.

## 5. Verificación de integración

- [ ] 5.1 Desde la Mac: probar el modo conversación de varios turnos y verificar que, al desactivarlo, el indicador del micrófono se apaga y el servidor no recibe audio.
- [ ] 5.2 Probar el modo un mensaje con "prende las luces": las luces deben reaccionar en 2 s o menos y la voz llegar después.
- [ ] 5.3 Medir con `ws_client.py` y con la PWA el tiempo al primer audio en una pregunta corta; el objetivo es 3 s o menos.
- [ ] 5.4 En el iPhone: instalar la PWA y repetir 5.1 y 5.2.
- [ ] 5.5 Verificar el acceso: un usuario no listado recibe 403 y el puerto no es alcanzable fuera de la tailnet.
- [ ] 5.6 Interrupción: verificar que un toque corta el audio en 200 ms o menos; que una interrupción por voz cambia de turno; y el escenario "¿cuál era el segundo?" de la spec. Contar falsos disparos en 10 respuestas largas por el altavoz de la Mac y del iPhone, sin audífonos, y ajustar el umbral.

## 6. PWA etapa B (diseño pro)

- [ ] 6.1 Elegir el framework de UI y definir el sistema visual (tipografía, color, modo oscuro) con el usuario.
- [ ] 6.2 Implementar la visualización del audio en tiempo real y las transiciones entre estados.
- [ ] 6.3 Iterar el diseño con el usuario hasta su aprobación.

## Workflow follow-up

- Abrir el PR con los artefactos de OpenSpec y la implementación, y hacer merge tras la revisión.
- Archivar el change (`/opsx:archive`) cuando el despliegue y la verificación estén completos.
