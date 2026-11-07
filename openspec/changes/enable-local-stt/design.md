# Design

## Context

- La imagen oficial instala sus extras base en `/opt/hermes/.venv` con `pm.build_env --record-selection`. `stt-whisper` no está entre ellos.
- El volumen `data/hermes` (en `/opt/data`, `HERMES_HOME`) hoy solo tiene `installs/<id>/bootstrap`, así que el gateway arranca desde el venv de la imagen (`HERMES_SITE=/opt/hermes/.venv/...`).
- `hermes pm install --extra X` no escribe en el venv de la imagen: crea una generación nueva del venv en `$HERMES_HOME/installs/<id>/environments/` y registra la selección. El Dockerfile oficial lo documenta: instalar un extra en runtime "builds a whole new venv generation on the volume", y el refresh de dependencias de stage2 restaura la base en los volúmenes al actualizar la imagen.
- Se probó una imagen propia con `RUN hermes pm install --extra stt-whisper`: la generación quedó en el `/opt/data` interno de la imagen, que el volumen tapa, y el venv de la imagen siguió sin `faster_whisper`. Se descartó.

El porqué está en proposal.md, y los requisitos en `specs/voice-transcription/spec.md`.

## Goals / Non-Goals

**Goals:**
- Habilitar el STT con el mecanismo que Hermes soporta, sin código propio ni cambios en Docker.
- Comprobar que la instalación persiste ante reinicio y recreación.

**Non-Goals:**
- Cambiar de modelo de Whisper (sigue `base`) o el proveedor de STT.
- Una imagen propia de Hermes.
- Automatizar la reinstalación: si la persistencia falla, se replantea el change.

## Decisions

### 1. `hermes pm install --extra stt-whisper` en runtime, como el usuario `hermes`
Se ejecuta como `docker exec -u 10000 finnip-brain hermes pm install --extra stt-whisper`.

- **Imagen propia (descartada):** no funciona, ver Context.
- **`pip install` dentro del contenedor (descartado):** el venv de la imagen está sellado y no tiene pip, y se perdería al recrear.
- **`pm install` (elegido):** es oficial, respeta `uv.lock`, guarda la generación y la selección en el volumen, y stage2 la mantiene al actualizar.
- Se ejecuta como uid 10000 para que los archivos del volumen queden con el dueño que usa el gateway.

### 2. Reinicio para adoptar la generación
El proceso del gateway ya en marcha sigue con el venv anterior. Después de instalar, `docker compose restart hermes` hace que arranque desde la generación nueva. Se verifica en `/proc/<pid>/environ` (`HERMES_SITE`) y con la importación de `faster_whisper` dentro del entorno seleccionado.

### 3. El modelo en el volumen
`faster-whisper` descarga el modelo `base` en la caché de Hugging Face, bajo `HOME=/opt/data`, en la primera transcripción. La primera nota de voz tarda más.

## Risks / Trade-offs

- [Una actualización de la imagen no conservara la selección] → Se verifica la recreación ahora. Tras cada actualización, la prueba con nota de voz del README lo detecta, y reinstalar es un solo comando documentado.
- [La generación ocupa varios cientos de MB en el volumen] → Hay unos 196 GB libres. `hermes pm gc` limpia las generaciones sin uso.
- [El primer arranque con la generación nueva o la primera transcripción tardan más] → Pasa una sola vez.
- [Unos 250 MB de RAM y CPU completa al transcribir] → Las notas de voz son cortas y `base` en int8 es ligero.

## Migration Plan

1. Respaldar `data/hermes/config.yaml`; la instalación no lo modifica, pero el respaldo es barato.
2. Ejecutar `docker exec -u 10000 finnip-brain hermes pm install --extra stt-whisper` y comprobar con `hermes pm status` que la selección incluye `stt-whisper`.
3. `docker compose restart hermes` y verificar el entorno del gateway y la importación.
4. Probar con una nota de voz, después con `--force-recreate` y otra nota de voz.

**Rollback:** `hermes pm install --without stt-whisper` (o `hermes pm repair`) y reiniciar. Los datos de Finnip no se tocan.
