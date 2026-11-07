# Tasks

## 1. Habilitar el STT local

- [x] 1.1 Respaldar `data/hermes/config.yaml`, ejecutar `docker exec -u 10000 finnip-brain hermes pm install --extra stt-whisper` y verificar con `hermes pm status` que la selección incluye `stt-whisper` y que la generación quedó en `data/hermes/installs/`
- [x] 1.2 Reiniciar con `docker compose restart hermes` y verificar que el gateway arranca (Telegram conectado y `finnip-voice` registrado), que su `HERMES_SITE` apunta a la generación nueva y que `faster_whisper` se importa en ese entorno

## 2. Verificación

- [x] 2.1 Transcribir una nota de voz en español con el STT de Hermes (por Telegram o con un archivo de prueba dentro del contenedor) y verificar que el texto sale en español y que `gateway.log` no registra `Voice transcription failed`; anotar el tiempo de transcripción
- [x] 2.2 Recrear el contenedor con `docker compose up -d --force-recreate hermes` y verificar de nuevo el entorno del gateway, la importación de `faster_whisper` y una transcripción, sin instalar nada a mano

## 3. Documentación

- [x] 3.1 Documentar en la sección "Voz" de `README.md` el comando de instalación, cómo verificar el STT y qué hacer si una actualización de Hermes lo pierde, y verificar que los comandos coinciden con los ejecutados en 1.1 y 2.2

## Workflow follow-up

- Abrir el PR con el change y el README, y hacer merge tras la revisión.
- Retomar las tareas 4.x de `add-telegram-voice-replies`.
- Archivar el change con `/opsx:archive` cuando la verificación esté completa.
