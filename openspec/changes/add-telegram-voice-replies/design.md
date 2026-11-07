# Design

## Context

Hermes (`nousresearch/hermes-agent`, contenedor `finnip-brain`) ya resuelve casi todo el flujo de voz en Telegram; lo verificamos en el código instalado:

- El STT local (faster-whisper `base`, `stt.language: "es"`) transcribe las notas de voz entrantes.
- `/voice on|tts|off` fija el modo por chat (`voice_only`, `all`, `off`) y lo persiste en `gateway_voice_mode.json`. Sin modo explícito, aplica `voice.auto_tts`, que equivale a `voice_only`.
- La nota de voz se envía después de la respuesta en texto. Si el proveedor declara `voice_compatible`, Hermes convierte a Ogg/Opus con `ffmpeg` (ya instalado en el contenedor) cuando el archivo no es `.ogg`.
- Los proveedores TTS de plugin se registran con `ctx.register_tts_provider()` y heredan de `agent.tts_provider.TTSProvider`. Reciben `tts.voice`, `tts.model`, `tts.speed` y `tts.output_format`. No requieren capabilities especiales.
- El único plugin existente, `finnip-lights`, es Python con biblioteca estándar y se prueba con `unittest`, con la red simulada.

El porqué del cambio está en proposal.md, y los requisitos en `specs/voice-replies/spec.md`.

## Goals / Non-Goals

**Goals:**
- Un proveedor `fish` mínimo, probado y sin dependencias nuevas.
- Reutilizar el flujo de voz de Hermes (modos, entrega y conversión) sin reimplementarlo.

**Non-Goals:**
- Streaming TTS (`stream()`) y reproducción por frases; queda para el Voice Gateway.
- Clonación de voces o búsqueda en el catálogo de Fish desde Finnip.
- Cambios en `compose.yaml`, Home Bridge o el STT.

## Decisions

### 1. Plugin TTS de Hermes en vez de proveedor `command` u OpenRouter
El plugin `finnip-voice` registra un `TTSProvider` llamado `fish`.

- **Proveedor `command` (descartado):** sería un script con `curl` en `tts.providers.fish`. Hermes limpia las variables de entorno de los subprocesos, así que habría que declarar `FISH_API_KEY` como passthrough; además, el escape de shell y el manejo de errores son más frágiles y difíciles de probar.
- **OpenRouter con el proveedor `openai` y `base_url` (descartado):** Hermes pide `response_format: opus` a los proveedores nativos de Opus, y OpenRouter solo acepta `mp3`/`pcm`. Tampoco tiene variante gratuita de Fish.
- **Plugin (elegido):** sigue el patrón de `finnip-lights`, es testeable con `unittest`, la key se lee en proceso con `os.environ` y declara `voice_compatible` para la conversión a Opus.

### 2. Formato: Opus nativo con respaldo de ffmpeg
- Si el formato pedido es `ogg` u `opus`, o si `output_path` termina en `.ogg`, se pide `format: "opus"` a Fish y se escribe en `.ogg`. En cualquier otro caso se pide `mp3`.
- La config fija `tts.output_format: opus`.
- Como `voice_compatible` es `True`, si el archivo no resulta `.ogg` Hermes lo convierte con `ffmpeg`.
- La tarea de verificación confirma que el `opus` de Fish viene en contenedor Ogg. Si no, se pide `mp3` y Hermes convierte, sin tocar la spec.

### 3. Defaults en el plugin, sobrescribibles por config
- Valores por defecto: voz `ae74d1059517440aa6e5d2d50598d179` y modelo `s2.1-pro-free`.
- `tts.voice` y `tts.model` los sobrescriben, mediante los kwargs `voice` y `model` que Hermes pasa al plugin.
- No se envía `language`: en Fish solo afecta la normalización del texto y, sin él, detecta el idioma solo. Así funciona igual cuando el usuario practica inglés.

### 4. HTTP con biblioteca estándar y errores saneados
- `urllib.request` hace `POST https://api.fish.audio/v1/tts` con los encabezados `Authorization: Bearer`, `Content-Type: application/json` y `model: <modelo>`, y `timeout=30`.
- Un error HTTP se convierte en `RuntimeError("Fish Audio devolvió HTTP <código>: <detalle corto>")`. El detalle se trunca y nunca incluye los encabezados de la petición.
- La key se lee en cada llamada. Si falta, falla antes de hacer cualquier petición.
- `synthesize` lanza la excepción y el dispatcher de Hermes arma el `{success: False}`. Como la voz se envía después del texto, el usuario recibe el texto de todos modos.
- Una respuesta vacía se trata como error y no se escribe ningún archivo, para no entregar una nota de voz vacía.

### 5. Modo por defecto: `voice.auto_tts: true`
- Finnip responde con voz cuando le hablan por voz.
- `/voice tts` activa la voz en todas las respuestas y `/voice off` la apaga. Ambos ya existen en Hermes.

### 6. Tests aislados de Hermes
- Los tests insertan un stub de `agent.tts_provider` en `sys.modules` antes de cargar el plugin, porque Hermes no está instalado en CI.
- Simulan `urlopen` igual que `finnip-lights` y verifican la URL, los encabezados, el cuerpo, el formato, los defaults, la key faltante, el saneamiento de errores y la respuesta vacía.

## Risks / Trade-offs

- [El modelo gratuito tiene límites de uso justo sin cifras y sin garantías de latencia] → Las respuestas de Finnip ya son cortas (SOUL.md). Ante un 429 o un error, el texto llega igual. Si hiciera falta, se cambia a `s2.1-pro` con `tts.model`, a $15 por millón de bytes.
- [La nota de voz llega unos segundos después del texto] → Es aceptable en Telegram. El streaming queda para el Voice Gateway.
- [La voz "Jarvis" es una voz pública de la comunidad, probablemente un clon de un actor de doblaje] → El usuario lo decidió para uso privado. Cambiar de voz es solo cambiar `tts.voice`.
- [Una actualización de la imagen de Hermes podría cambiar la API de `TTSProvider`] → Los tests fijan el contrato que usamos, y la prueba manual tras actualizar Hermes lo detecta.
- [Los caracteres acentuados cuentan como 2 bytes] → No importa en el modelo gratuito; sí en el de pago.

## Migration Plan

1. Hacer merge del PR. El despliegue requiere aprobación explícita, según `AGENTS.md`.
2. Respaldar `data/hermes/config.yaml` y copiar `apps/finnip-voice/` a `data/hermes/plugins/finnip-voice/`.
3. En `config.yaml`, agregar `finnip-voice` a `plugins.enabled` y fijar `tts.provider: fish`, `tts.output_format: opus` y `voice.auto_tts: true`.
4. Validar el YAML, reiniciar `hermes`, mandar `/new` y probar con una nota de voz.

**Rollback:** restaurar el respaldo de `config.yaml` y reiniciar. `/voice off` lo desactiva al instante sin reiniciar.
