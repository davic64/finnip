# Proposal

## Why

Finnip no puede transcribir las notas de voz de Telegram. La imagen `nousresearch/hermes-agent:latest` no incluye el extra `stt-whisper`, así que Hermes responde `No STT provider available. Install faster-whisper` aunque `stt.local` esté configurado. Sin STT, el change `add-telegram-voice-replies` no puede completar su verificación, porque la voz responde a notas de voz que hoy no se entienden.

## What Changes

- Instalar el extra `stt-whisper` (`faster-whisper` fijado por el `uv.lock` de Hermes) con el mecanismo oficial, `hermes pm install --extra stt-whisper`, dentro de `finnip-brain`. Hermes crea una generación del venv en el volumen (`data/hermes/installs/`) y registra la selección, así que el extra sobrevive a reinicios, a recreaciones del contenedor y a actualizaciones de la imagen.
- Documentar en `README.md` cómo habilitar, verificar y restaurar el STT local.
- Sin cambios en `compose.yaml`, en la imagen ni en el código. Se descartó una imagen propia: su build instala el extra en el `/opt/data` interno de la imagen, que el volumen tapa en runtime.

## Capabilities

### New Capabilities
- `voice-transcription`: transcripción local de las notas de voz que Finnip recibe, y su permanencia ante reinicios, recreaciones y actualizaciones de Hermes.

### Modified Capabilities

## Impact

- **Runtime**: una generación nueva del venv en `data/hermes/installs/` (cientos de MB) y el modelo `base` de Whisper descargado una vez en `data/hermes` (unos 150 MB). El primer arranque tras la instalación usa esa generación.
- **Recursos**: unos 250 MB de RAM extra con el modelo cargado y CPU completa durante cada transcripción (i5-6300U).
- **Docker**: sin cambios.
- **Relación**: desbloquea las tareas 4.x de `add-telegram-voice-replies`.
