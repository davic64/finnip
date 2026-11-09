# Design

## Context

Estado medido el 2026-11-09:

- `voice-gateway` ya detecta preguntas sobre el servidor con palabras clave (`text.wants_stats`), mide `/proc`, manda `{"type": "stats"}` a la PWA y antepone los números al prompt. La PWA (`hud.ts`) muestra 4 medidores y los oculta cuando Finnip termina de hablar.
- `voice-gateway` ya habla con `home-bridge` (`BRIDGE_API_KEY`) para leer el color de los monitores.
- Home Assistant no tiene entidades `calendar.*` ni `weather.*`, y tiene una sola entidad `notify`.
- La PWA tiene service worker y manifest, así que puede recibir Web Push.
- El por qué está en proposal.md y los requisitos en `specs/`.

## Goals / Non-Goals

**Goals:**

- Que cada panel aparezca a la vez que la respuesta y diga los mismos datos que Finnip.
- Agregar un panel nuevo cuesta un detector, un lector de datos y un renderizador, sin tocar el protocolo.
- Ninguna credencial pasa por el chat ni por el repo.

**Non-Goals:**

- Escritura en Gmail.
- Un panel que se quede fijo en pantalla (tipo dashboard). Por ahora los paneles viven mientras Finnip habla.
- Notificaciones push, Apple Music y GitHub (pospuestos por el usuario).

## Decisions

### 1. Un evento `panel` genérico

`{"type": "panel", "kind": "calendar" | "weather" | "mail" | "server", "data": {...}}`.

`stats` se migra a `kind: "server"`. Cada `kind` tiene en el gateway un detector (palabras clave, como `wants_stats`), un lector `async` y un formateador de nota para el prompt. En la PWA tiene un renderizador. Si una frase coincide con varios paneles, se muestran uno tras otro (máximo 2).

Alternativa descartada: que Hermes pida el panel con una herramienta. Es más flexible, pero el panel saldría después de la llamada a la herramienta (1-3 s más tarde) y no a la par de la respuesta.

### 2. Calendario y clima por Home Assistant

HA ya está, ya maneja OAuth y refresca los tokens. `home-bridge` agrega:

- `GET /calendar?days=N`: eventos de todas las entidades `calendar.*`.
- `POST /calendar/events`: crea un evento con el servicio `calendar.create_event`.
- `GET /weather`: estado actual y pronóstico (`weather.get_forecasts`).

Nota: la integración de Google Calendar en HA exige que el usuario cree credenciales OAuth en Google Cloud. Ese mismo proyecto sirve para Gmail (decisión 3).

### 3. Gmail directo con la API de Google

HA no lee Gmail. Un lector en `voice-gateway` usa `gmail.readonly` con un refresh token. El usuario lo autoriza una vez corriendo `tools/google_auth.py` en el servidor con `ssh -t` y pegando el código en su terminal. El token queda en `config/google-token.json` (modo 600). Solo se muestran remitente, asunto y hora de los no leídos de la bandeja principal.

## Risks / Trade-offs

- **Palabras clave:** algo como "¿tengo algo hoy?" puede no detectarse. Mitigación: lista amplia y, si falla, Finnip todavía tiene las herramientas, solo que sin panel.
- **Más secretos en el servidor.** Mitigación: todos van en `config/` con modo 600, son de solo lectura donde se puede, y nunca se imprimen en logs.
- **Latencia:** cada lector agrega tiempo antes del modelo. Mitigación: corren en paralelo con un límite de 1.5 s y, si se pasan, el panel se omite.
