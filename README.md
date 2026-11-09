# Finnip

Asistente personal autoalojado. Recibe órdenes en lenguaje natural por
Telegram y controla dispositivos del hogar mediante Home Assistant.

## Arquitectura

```
PWA finnip-app ──wss (tailscale serve)──► voice-gateway ──/v1/responses──┐
                                           STT faster-whisper · Edge TTS   │
Telegram ───────────────────────────────────────────────────────────────► Hermes Agent (finnip-brain)
             ├─ plugin finnip_voice ──HTTPS + Bearer──► Fish Audio (respuestas habladas)
             └─ plugin finnip_lights ──HTTP + Bearer──► Home Bridge (finnip-home-bridge)
                                                          └─ REST ──► Home Assistant (finnip-homeassistant)
                                                                        └─ Bluetooth ──► light.leds_monitores
```

| Servicio | Contenedor | Función |
|---|---|---|
| `hermes` | `finnip-brain` | Agente de IA conectado a Telegram. Carga los plugins `finnip_lights` y `finnip_voice`. |
| `home-bridge` | `finnip-home-bridge` | API TypeScript (Fastify + Zod). Único punto de acceso de Hermes a Home Assistant. |
| `homeassistant` | `finnip-homeassistant` | Domótica. Red del host y D-Bus para Bluetooth (integración `elkbledom`). |
| `voice-gateway` | `finnip-voice-gateway` | Conversación por voz en tiempo real (WebSocket `/ws`) y la PWA. Solo por Tailscale. |

Hermes nunca recibe `HA_TOKEN`: solo conoce `BRIDGE_API_KEY` y una lista
cerrada de operaciones expuestas por Home Bridge.

## Estructura

```
apps/
  home-bridge/     API TypeScript, pruebas Vitest y Dockerfile (ver su README)
  finnip-lights/   Plugin Python de Hermes: herramienta finnip_lights
  finnip-voice/    Plugin Python de Hermes: proveedor TTS fish (Fish Audio)
  voice-gateway/   Servicio Python (Starlette): /ws, STT, Hermes en streaming, TTS por frase
  finnip-app/      PWA (Vite + TypeScript): modos de micrófono, interrupción, reproducción
compose/
  compose.yaml     Definición de los servicios
config/            Variables de entorno con secretos (no versionado)
data/              Datos persistentes de Hermes y Home Assistant (no versionado)
backups/           Respaldos locales (no versionado)
```

## Configuración

Crear con permisos `600`:

- `config/homeassistant.env`: `HA_TOKEN` y `BRIDGE_API_KEY` (mínimo 32 caracteres).
- `config/hermes-bridge.env`: `BRIDGE_API_KEY`, con el mismo valor.
- `data/hermes/.env`: `FISH_API_KEY` de Fish Audio, para la voz de Finnip.
- `config/voice-gateway.env`: `API_SERVER_KEY` (el mismo de `data/hermes/.env`),
  `ALLOWED_TAILSCALE_USERS` (logins separados por coma) y, opcional,
  `STT_INITIAL_PROMPT`, `VOICE_MODEL` (por ejemplo `claude-haiku-5-5`) y `TTS_VOICE`.

`HA_URL` y `FINNIP_BRIDGE_URL` se definen en `compose/compose.yaml`.

## Operación

Desde `compose/`:

```sh
sudo docker compose up -d                          # levantar todo
sudo docker compose up -d --build home-bridge      # desplegar cambios de la API
sudo docker compose logs --tail=50 <servicio>
```

Las variables de entorno se leen al crear el contenedor: tras cambiar un
`.env`, recrear el servicio con `--force-recreate`; `restart` no basta.

Para actualizar los plugins:

```sh
sudo cp apps/finnip-lights/*.py apps/finnip-lights/plugin.yaml data/hermes/plugins/finnip-lights/
sudo cp apps/finnip-voice/*.py apps/finnip-voice/plugin.yaml data/hermes/plugins/finnip-voice/
sudo docker compose restart hermes
```

## Voz

Finnip transcribe las notas de voz con el STT local de Hermes y contesta con
voz mediante el plugin `finnip-voice`, que registra el proveedor TTS `fish`
(Fish Audio, modelo `s2.1-pro-free`, voz `ae74d1059517440aa6e5d2d50598d179`).
El audio llega como nota de voz Ogg/Opus, siempre después de la respuesta en
texto; si Fish Audio falla, solo llega el texto.

En `data/hermes/config.yaml`:

```yaml
plugins:
  enabled:
    - finnip-lights
    - finnip-voice
tts:
  provider: fish
  output_format: opus
  # voice: <reference_id>   # opcional, otra voz de Fish Audio
  # model: s2.1-pro         # opcional, modelo de pago
voice:
  auto_tts: true            # responde con voz a las notas de voz
stt:
  language: "es"
```

Por chat de Telegram: `/voice on` (voz solo ante notas de voz), `/voice tts`
(voz en todas las respuestas) y `/voice off` (solo texto).

### Transcripción local (STT)

La imagen de Hermes no incluye `faster-whisper`. Se habilita una vez con el
gestor de dependencias de Hermes, que guarda el entorno en el volumen
(`data/hermes/installs/`), así que sobrevive a reinicios y recreaciones:

```sh
sudo docker exec -u 10000 finnip-brain hermes pm install --extra stt-whisper
cd compose && sudo docker compose restart hermes
```

Verificar que sigue habilitado (por ejemplo, tras actualizar Hermes):

```sh
sudo docker exec -u 10000 finnip-brain hermes pm status | grep -c stt-whisper   # 1 = habilitado
```

Si devuelve `0` o el log muestra `No STT provider available`, repetir la
instalación. El modelo `base` (~150 MB) se descarga en el volumen con la
primera nota de voz.

## Interfaz de voz (PWA)

`https://finnip.tail7d805f.ts.net`, solo desde dispositivos de la tailnet con un
usuario de `ALLOWED_TAILSCALE_USERS`. En el iPhone: Safari → Compartir →
**Añadir a pantalla de inicio**.

- **Conversación**: el orbe abre el micrófono y queda escuchando; cada frase es un turno.
  "Terminar conversación" cierra el micrófono por completo.
- **Un mensaje**: el orbe escucha una frase y se cierra solo.
- **Interrumpir**: tocar el orbe mientras Finnip habla. En modo conversación también
  hablando encima (se desactiva en Ajustes → Interrumpir con la voz).

Publicación con Tailscale (una vez, en el host):

```sh
sudo tailscale serve --bg --https=443 http://127.0.0.1:8765
```

`voice-gateway` solo escucha en `127.0.0.1:8765` del host y exige el encabezado
`Tailscale-User-Login` que pone `tailscale serve`. Habla con Hermes por su API
server (`API_SERVER_HOST=0.0.0.0` en la red interna de Compose, sin puerto
publicado). El protocolo de `/ws`, que también usará el ESP32, está en
`openspec/changes/add-voice-interface/design.md`; `apps/voice-gateway/tools/ws_client.py`
es un cliente de referencia que mide la latencia.

Desplegar cambios:

```sh
# PWA: recompilar basta, dist/ está montado en el contenedor
cd apps/finnip-app && sudo docker run --rm -u $(id -u):$(id -g) -e HOME=/tmp -v "$PWD":/app -w /app node:22-slim sh -c "npm ci && npm run build"
# Backend
cd compose && sudo docker compose up -d --build voice-gateway
```

## Dispositivos

Finnip solo ve las entidades de Home Assistant con la etiqueta `finnip` y de un
dominio permitido (`light`, `switch`, `cover`, `climate`). Para agregar un
dispositivo basta con etiquetarlo en Home Assistant: no hay que cambiar código
ni desplegar. Sus acciones se deducen de los atributos que reporta Home
Assistant (color, brillo, posición, temperatura, modos).

La herramienta `finnip_lights` acepta en `device` el nombre del dispositivo
(sin importar mayúsculas ni acentos) o su `entity_id`, así que actúa sin llamar
antes a `action=list`. Si el nombre no coincide o es ambiguo, el error incluye
los dispositivos disponibles.

## Home Bridge

Rutas autenticadas con `Authorization: Bearer <BRIDGE_API_KEY>`:

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/health` | Estado del servicio (público) |
| `GET` | `/devices` | Dispositivos expuestos y sus `capabilities` |
| `GET` | `/devices/:id` | Estado de un dispositivo |
| `POST` | `/devices/:id/:action` | Ejecuta una capability y confirma el estado |

Detalle de acciones y cuerpos en `apps/home-bridge/README.md`. Las órdenes
devuelven `confirmed` y `actual` con el estado que reporta Home Assistant después
de ejecutarlas. La imagen Docker solo se construye si pasan la comprobación de
tipos y las pruebas.
