# Proposal

## Why
Con un proyecto corriendo en pantalla, lo natural es señalar: "haz esto más grande", "cambia el color de aquí". Claude Code no sabe qué es "esto" si solo recibe las palabras.

## What Changes
- **Señalar en pantalla:**
  - Cuando el usuario habla de "esto", "aquí" o "este botón", Finnip manda la tarea con `point`.
  - La app de la Mac oculta el holograma un instante y captura la zona alrededor del puntero del mouse (1400 × 900 puntos, JPEG, con el puntero dibujado).
  - La captura se guarda en `.finnip/` del proyecto (fuera de git), y la orden de Claude Code empieza con una nota: dónde está la captura y en qué porcentaje de ella está el puntero.
- **En la nube:** el gateway le pide la captura a la Mac y se la pasa al servicio del servidor, que la guarda en el proyecto igual.
- **Permiso:** la primera vez, macOS pide permiso de Grabación de pantalla para Finnip.
- **Fuera de alcance:** que Finnip haga clic o escriba en la app ("dale clic aquí").

## Capabilities

### Modified Capabilities
- `voice-projects`: las tareas pueden ir con una captura de lo que el usuario señala con el mouse.
