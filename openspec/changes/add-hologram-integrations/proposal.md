# Proposal

## Why

La interfaz holográfica ya muestra el estado del servidor mientras Finnip habla de él. El usuario quiere lo mismo para su día a día:

- Ver en el holograma su agenda de Google Calendar, el clima y sus correos de Gmail, solo mientras Finnip habla de eso.

Hoy Finnip no tiene acceso a calendario, clima ni correo.

## What Changes

- **Paneles holográficos genéricos.** El HUD del estado del servidor se generaliza en "paneles":
  - `voice-gateway` detecta de qué habla el usuario (servidor, agenda, clima, correo).
  - Pide los datos antes de llamar al modelo, los manda a la PWA como un evento `panel` y los inyecta en el prompt. Así Finnip dice exactamente lo que se ve y no gasta tiempo en herramientas.
  - La PWA dibuja cada panel en el estilo holográfico y lo oculta cuando Finnip termina de hablar.
- **Google Calendar vía Home Assistant.** El usuario agrega la integración oficial de Google Calendar en HA (él hace el login de Google). `home-bridge` expone los eventos y la creación de eventos. Finnip también puede consultarlos y crearlos por voz o Telegram.
- **Clima vía Home Assistant** con la integración Met.no (gratis, sin clave), expuesto por `home-bridge`.
- **Gmail** de solo lectura con la API de Google (`gmail.readonly`). Usa el mismo proyecto de Google Cloud que pide HA para el calendario. El token lo autoriza el usuario y vive en el servidor.
- El micrófono se silencia mientras Finnip habla. Se interrumpe con un toque, no con la voz. Esto ya está en la rama de voz y aquí solo se documenta.

**Fuera de alcance (por ahora):** notificaciones push al teléfono, Apple Music, GitHub, enviar o borrar correos, y acceso fuera de Tailscale.

## Capabilities

### New Capabilities

- `hologram-panels`: paneles de datos (servidor, agenda, clima, correo) que aparecen en el holograma mientras Finnip habla de ellos.

### Modified Capabilities

## Impact

- `apps/voice-gateway`: módulo de paneles.
- `apps/home-bridge`: rutas de calendario y clima.
- `apps/finnip-app`: renderizadores de panel.
- Plugins de Hermes: herramientas de calendario.
- Home Assistant: integraciones Google Calendar y Met.no (las agrega el usuario).
- Secreto nuevo en `config/`: token de Gmail. Nunca se muestran ni se suben al repo.
