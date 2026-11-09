# Design

## Context

Estado del servidor `finnip` medido el 2026-11-09:

- **Hermes** (`finnip-brain`):
  - Transcribe con faster-whisper `base` en CPU/int8 (`stt.provider: local`).
  - Sintetiza con Edge TTS (`tts.provider: edge`, voz `es-MX-JorgeNeural`).
  - Usa `claude-sonnet-5-5` como modelo principal.
- **API server de Hermes:** ya está activo, pero escucha solo en `127.0.0.1:8642` dentro del contenedor.
  - Expone `/v1/chat/completions` y `/v1/responses` (compatibles con OpenAI, con `stream`) y `/v1/runs`.
  - Se autentica con `API_SERVER_KEY`.
- **Atajo de luces:** `finnip-lights` registra un hook `pre_llm_call`. Si el mensaje es una orden simple de encender o apagar, la ejecuta contra Home Bridge antes de llamar al modelo. Corre dentro de Hermes, así que aplica a cualquier canal, incluido el API server.
- **Tiempos de un turno de voz en Telegram:** STT unos 1.3 s, cada llamada al modelo de 1.4 a 5 s, Edge TTS de 1.5 a 3 s por respuesta. A eso se suman 1–3 s de Telegram.
- **El repo** tiene `home-bridge` (TypeScript/Fastify) y los plugins en Python con `unittest`. Las reglas de `AGENTS.md` piden pruebas, ramas por feature y aprobación para tocar Docker o desplegar.

El porqué está en proposal.md, y los requisitos en `specs/voice-interface/spec.md`.

## Goals / Non-Goals

**Goals:**

- Que el primer audio de respuesta empiece a sonar en 3 s o menos tras terminar de hablar, en una respuesta corta.
- Dos modos de micrófono claros, con la garantía de que el micrófono está cerrado cuando el modo está desactivado.
- Poder interrumpir a Finnip con un toque o con la voz, sin que su propia voz lo interrumpa.
- Un protocolo de cliente simple, que el ESP32 pueda implementar sin la PWA.
- Reutilizar Hermes (memoria, herramientas, `SOUL.md`, el atajo de luces) sin duplicar la lógica del agente.

**Non-Goals:**

- Palabra de activación.
- STT con resultados parciales en streaming. Se transcribe cada frase completa al cerrarla el VAD.
- Firmware del ESP32.

## Decisions

### 1. `voice-gateway` en Python, separado de Hermes

Es un servicio nuevo (`apps/voice-gateway/`, Starlette + uvicorn) en su propio contenedor.

- **Python en vez de TypeScript:** faster-whisper y edge-tts son bibliotecas de Python. En TypeScript haría falta un segundo proceso para STT y TTS.
- **Separado de Hermes en vez de un plugin de plataforma:** Hermes no está pensado para audio en tiempo real. Un servicio aparte se reinicia y se prueba sin tocar el agente, y el ESP32 se conecta al mismo punto.
- **Costo:** un segundo modelo faster-whisper `base` en memoria (unos 150 MB). Es aceptable en el EliteBook.

### 2. Hermes vía `/v1/responses` con streaming y una conversación fija

`voice-gateway` envía cada transcripción a `POST /v1/responses` con `stream: true` y `conversation: "finnip-voice"`. Así la PWA mantiene su propio hilo continuo, separado del de Telegram.

- Hermes pasa a escuchar en la red de Compose con `API_SERVER_HOST=0.0.0.0`, sin publicar el puerto en el host. Solo los contenedores de `compose_default` lo alcanzan.
- La clave `API_SERVER_KEY` vive en `config/voice-gateway.env` y nunca llega al cliente.
- **A verificar en la tarea 1.2:** si una petición del API server puede marcarse como turno de voz, para usar la ruta `auxiliary.voice_chat`. Si no se puede, se usa el modelo principal.

### 3. Respuesta frase por frase

`voice-gateway` acumula el texto del stream y lo corta en frases (`.`, `?`, `!`, `:` o un máximo de unos 200 caracteres). Por cada frase:

1. La sintetiza con Edge TTS (`es-MX-JorgeNeural`, MP3).
2. Envía el audio al cliente en cuanto está listo, en orden.

La síntesis de la frase N+1 corre mientras suena la N. El cliente reproduce los fragmentos en cola con la Web Audio API, sin huecos.

### 4. VAD en el cliente y STT por frase en el servidor

- La PWA detecta voz con `@ricky0123/vad-web` (Silero en el navegador) y envía PCM16 mono de 16 kHz mientras hay voz.
- Al detectar el final de la frase manda `utterance_end`, y el servidor transcribe ese bloque con faster-whisper (`language: es`, `vad_filter`, el mismo `initial_prompt` que Hermes).
- **Por qué en el cliente:** solo sube audio con voz, y el ESP32 puede usar su propio VAD o un botón con el mismo protocolo.

### 5. Modos de micrófono

- **Conversación:** el botón abre el micrófono (`getUserMedia` con `echoCancellation: true`, `noiseSuppression: true`) y lo mantiene abierto, también mientras Finnip habla, para permitir la interrupción por voz (decisión 9). Al apagar el modo se detienen todas las pistas del `MediaStream`, el indicador del micrófono del sistema se apaga y se cierra el procesamiento.
- **Un mensaje:** un toque abre el micrófono, el primer `utterance_end` lo cierra y la respuesta se reproduce con el micrófono ya cerrado. Aquí solo se puede interrumpir con un toque.
- El estado visible (apagado, escuchando, pensando, hablando) refleja el estado real del micrófono, no una suposición.

### 6. Protocolo del WebSocket (`/ws`)

Es el mismo para la PWA y para el ESP32.

**Del cliente al servidor:**
- Mensajes JSON de control: `{"type":"hello","client":"pwa|esp32","version":1}`, `{"type":"utterance_end"}`, `{"type":"cancel"}` y `{"type":"interrupt","played_seq":n,"played_ms":m}`.
- Frames binarios con PCM16 LE mono de 16 kHz.

**Del servidor al cliente:**
- JSON `{"type":"transcript","text":...}`.
- JSON `{"type":"reply_text","text":...}`, por frase.
- Frames binarios con el audio de cada frase, precedidos de `{"type":"audio","seq":n,"format":"mp3"}`.
- JSON `{"type":"done"}` y `{"type":"error","message":...}`.

`cancel` detiene el turno en curso: corta el stream de Hermes y la síntesis pendiente. `interrupt` hace lo mismo, e informa además hasta qué fragmento (`played_seq`) y cuántos milisegundos del último (`played_ms`) sonaron, para la decisión 9.

### 7. Acceso solo por Tailscale

- `tailscale serve` publica `voice-gateway` con HTTPS en `https://finnip.<tailnet>.ts.net`. El navegador exige HTTPS para usar el micrófono.
- El contenedor publica su puerto solo en `127.0.0.1` del host.
- `voice-gateway` acepta peticiones únicamente si traen el encabezado `Tailscale-User-Login` y ese usuario está en `ALLOWED_TAILSCALE_USERS`. Las peticiones locales sin ese encabezado se rechazan.

### 8. PWA en etapas

- **Etapa A (funcional):** Vite + TypeScript, el botón de cada modo, el estado, la transcripción y la respuesta en pantalla, la reproducción en cola y las métricas de latencia visibles en modo debug.
- **Etapa B (diseño pro):** sistema visual, una visualización del audio animada en tiempo real, transiciones y modo oscuro, con iteraciones revisadas por el usuario. El framework de la UI se decide al empezar la etapa B, sin bloquear la A.

### 9. Interrupción

**Formas de interrumpir:**
- **Con un toque:** en cualquier modo, tocar el botón o la zona central mientras Finnip habla lo interrumpe. Es la forma garantizada.
- **Con la voz (barge-in):** en modo conversación, si el VAD detecta voz del usuario mientras Finnip habla, se interrumpe. Se puede desactivar en ajustes ("Interrumpir con la voz"); por defecto está activo.

**Al interrumpir:**
1. La PWA detiene la reproducción y vacía la cola de audio de inmediato, sin esperar al servidor.
2. La PWA envía `interrupt` con `played_seq` y `played_ms`.
3. El servidor cancela el stream de Hermes (cierra la conexión SSE y, si aplica, `POST /v1/runs/{id}/stop`) y la síntesis pendiente.
4. La nueva frase del usuario se procesa como un turno normal.

**Evitar que Finnip se interrumpa a sí mismo (eco):**
- **Cancelación de eco del navegador** (`echoCancellation`). Con audífonos el riesgo casi desaparece.
- **Umbral más exigente mientras Finnip habla:** se sube el `positiveSpeechThreshold` del VAD y hacen falta unos 300 ms de voz continua (`minSpeechFrames`) para disparar la interrupción.
- **Descarte por similitud en el servidor:** si la transcripción del audio que disparó la interrupción se parece (similitud de 0.6 o más) al texto de las frases que Finnip estaba diciendo, se trata como eco. Se descarta y se envía `{"type":"resume"}` al cliente.
- **Contrapartida:** los 300 ms de espera retrasan un poco la interrupción por voz. El toque es inmediato.

**Lo que el usuario alcanzó a oír:**
- El servidor guarda qué texto corresponde a cada `seq`. Con `played_seq` y `played_ms` arma lo oído: las frases completas reproducidas, más la frase cortada marcada como incompleta.
- El siguiente turno a Hermes se envía con una nota antes del mensaje del usuario: `[El usuario interrumpió tu respuesta anterior; solo alcanzó a oír: "..."]`. Así Finnip no da por dicho lo que no se oyó.
- La tarea 1.4 revisa si el API server permite reemplazar la respuesta guardada. Si lo permite, se usa eso en vez de la nota.

## Risks / Trade-offs

- **Eco en modo conversación con altavoz:** puede provocar falsas interrupciones. Lo mitigan las tres capas de la decisión 9, y la interrupción por voz se puede apagar.
- **Interrupción por ruido** (otra persona hablando, la tele): el umbral alto lo reduce. Si en algún lugar molesta, se apaga la interrupción por voz y queda el toque.
- **Edge TTS no oficial:** si deja de funcionar, se cambia de proveedor en `voice-gateway` sin tocar el protocolo. Piper ya se midió en el servidor como alternativa local (2–3 s).
- **iOS:** Safari suspende el audio y el micrófono de una PWA en segundo plano, así que la conversación solo funciona con la app en primer plano.
- **Doble modelo Whisper:** son unos 150 MB más de RAM. Si molesta, Hermes podría volver a STT por API en Telegram.
- **Exponer el API server de Hermes a la red de Compose:** queda protegido por `API_SERVER_KEY` y sin puerto publicado en el host.

## Migration Plan

1. Desplegar `voice-gateway` y abrir el API server de Hermes a la red interna, con aprobación.
2. Configurar `tailscale serve` y probar desde la Mac.
3. Instalar la PWA en el iPhone.
4. Telegram sigue igual todo el tiempo.

**Rollback:** detener el contenedor `voice-gateway`, quitar `API_SERVER_HOST` y deshacer `tailscale serve`.

## Open Questions

- ¿El API server de Hermes permite marcar una petición como turno de voz, para usar `auxiliary.voice_chat`?
- ¿Qué framework de UI se usa en la etapa B? Se decide al iniciarla.
- ¿El API server permite reemplazar una respuesta guardada para dejar solo la parte oída? Si no, se usa la nota en el siguiente turno.
- ¿Cuántos falsos disparos hay con el altavoz de la Mac y del iPhone, sin audífonos? Se mide en la tarea 5.6 para ajustar el umbral.
