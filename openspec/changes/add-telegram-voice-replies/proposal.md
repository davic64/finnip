# Proposal

## Why

Finnip solo responde por texto en Telegram. Para que se sienta como un asistente estilo JARVIS, y como paso previo a la plataforma de voz (Mac, PWA, ESP32), debe poder contestar con su propia voz. Hermes ya transcribe las notas de voz entrantes (STT local, ahora en español) y ya sabe entregar notas de voz en Telegram, pero ningún proveedor TTS integrado ofrece Fish Audio: el único camino gratuito con la voz elegida es la API directa de Fish Audio (`s2.1-pro-free`). OpenRouter se descartó: no tiene variante gratuita de Fish y solo entrega `mp3`/`pcm`, mientras Hermes pide `opus` a los proveedores compatibles con OpenAI.

## What Changes

- Nuevo plugin de Hermes `finnip-voice` (Python, en `apps/finnip-voice/`) que registra un proveedor TTS llamado `fish` mediante `PluginContext.register_tts_provider()`.
- El proveedor llama a `POST https://api.fish.audio/v1/tts` con el modelo `s2.1-pro-free`, la voz `ae74d1059517440aa6e5d2d50598d179` ("Jarvis", español) y salida Opus para que Telegram la muestre como nota de voz.
- La API key se lee de `FISH_API_KEY` en el `.env` de Hermes; nunca se registra en logs ni se devuelve al modelo.
- Configuración de Hermes (con aprobación al desplegar): habilitar el plugin, `tts.provider: fish` y `voice.auto_tts: true`, de modo que Finnip responda con voz cuando el usuario le mande una nota de voz. El usuario puede cambiar a voz en todas las respuestas con `/voice tts` o desactivarla con `/voice off`.
- Pruebas `unittest` del plugin con la API simulada y un job nuevo en CI.
- Sin cambios en Home Bridge, Home Assistant ni en `compose.yaml`.

## Capabilities

### New Capabilities
- `voice-replies`: síntesis de la voz de Finnip y entrega de respuestas habladas en Telegram (proveedor, voz, formato, cuándo se habla y cómo falla).

### Modified Capabilities

## Impact

- **Código nuevo**: `apps/finnip-voice/` (plugin, `plugin.yaml`, tests) y un job en `.github/workflows/ci.yml`.
- **Runtime**: `data/hermes/plugins/finnip-voice/`, `data/hermes/config.yaml` (`plugins.enabled`, `tts`, `voice`) y `FISH_API_KEY` en `data/hermes/.env` (ya agregada).
- **Dependencias**: ninguna nueva; solo la biblioteca estándar de Python. `ffmpeg` ya está en el contenedor.
- **Externo**: la API de Fish Audio; el modelo gratuito tiene límites de uso justo sin cifras publicadas y sin garantías de latencia.
- **Documentación**: `README.md` (arquitectura, configuración y despliegue del plugin).
