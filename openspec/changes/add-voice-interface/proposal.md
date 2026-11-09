# Proposal

## Why

Hoy Finnip solo se usa por voz a través de notas de Telegram. Ese canal tiene un límite de latencia que no se puede bajar desde Hermes:

- El audio solo sale cuando el usuario termina de grabar y lo envía completo.
- La respuesta tiene que llegar como un archivo de voz terminado, así que no se puede empezar a reproducir mientras se genera.
- Medido en el servidor el 2026-11-09: una respuesta de voz tarda unos 6.5 s desde que llega el audio, más 1–3 s de Telegram. Una orden de luces por el atajo `finnip-lights` tarda unos 1.5 s.

Una interfaz propia permite enviar el audio en streaming, reproducir la respuesta frase por frase y controlar el micrófono con precisión. También define el protocolo que después usará el dispositivo ESP32, para que el hardware sea solo otro cliente.

## What Changes

- Nuevo servicio `voice-gateway` (contenedor nuevo en `compose.yaml`) con una conexión WebSocket por cliente:
  - Recibe audio PCM del cliente.
  - Lo transcribe con faster-whisper local.
  - Envía el texto a Hermes por su API server, en streaming.
  - Sintetiza cada frase con Edge TTS y la devuelve al cliente en cuanto está lista.
- Nueva PWA `finnip-app` servida por `voice-gateway`, instalable en iPhone y Mac. Tiene dos modos de micrófono:
  - **Conversación:** un botón abre el micrófono y lo deja escuchando. La detección de voz (VAD) separa los turnos. Al desactivarlo, el micrófono se cierra por completo.
  - **Un mensaje:** un toque abre el micrófono para una sola frase. Se cierra solo cuando el VAD detecta que terminó.
- El usuario puede **interrumpir a Finnip** mientras habla, de dos formas: con un toque o hablando encima (barge-in). La interrupción por voz se puede desactivar. Finnip se calla al instante y el siguiente turno sabe qué parte de su respuesta alcanzó a oír el usuario.
- El acceso es solo por Tailscale (`tailscale serve` con HTTPS en `*.ts.net`), con una lista de usuarios permitidos. Nada queda expuesto a internet.
- El API server de Hermes pasa a escuchar en la red interna de Docker (`API_SERVER_HOST`) para que `voice-gateway` lo alcance. Requiere aprobación al desplegar.
- El atajo de luces de `finnip-lights` (hook `pre_llm_call`) se reutiliza sin cambios, porque corre dentro de Hermes para cualquier canal.
- Telegram se mantiene como canal de respaldo, sin cambios.
- La interfaz se construye por etapas: primero la PWA funcional y medible; el diseño visual "pro" va en una etapa posterior dentro de este mismo change.

**Fuera de alcance:** firmware del ESP32, palabra de activación ("Hey Finnip"), acceso fuera de Tailscale y multiusuario.

## Capabilities

### New Capabilities

- `voice-interface`: conversación por voz con Finnip desde una PWA propia. Cubre los modos de micrófono, la interrupción, el streaming de audio de ida y vuelta, el protocolo de cliente reutilizable por el ESP32 y la restricción de acceso.

### Modified Capabilities

## Impact

- **Código nuevo:**
  - `apps/voice-gateway/` (servicio Python, tests).
  - `apps/finnip-app/` (PWA en TypeScript).
  - Un job nuevo en `.github/workflows/ci.yml`.
- **Runtime:**
  - `compose/compose.yaml`: servicio `voice-gateway`, y `API_SERVER_HOST`/`API_SERVER_PORT` para `hermes`.
  - `config/voice-gateway.env`: clave del API server y lista de usuarios de Tailscale.
  - Configuración de `tailscale serve` en el host.
- **Dependencias nuevas:**
  - Backend: `faster-whisper`, `edge-tts`, un servidor ASGI (`starlette` + `uvicorn`).
  - PWA: Vite y un VAD en el navegador (`@ricky0123/vad-web`).
- **Recursos:** un segundo modelo faster-whisper `base` en memoria (unos 150 MB) además del de Hermes.
- **Externo:** Edge TTS usa un servicio de Microsoft no oficial que puede cambiar sin aviso. Telegram queda como respaldo.
- **Documentación:** `README.md` (arquitectura, despliegue, instalación de la PWA).
