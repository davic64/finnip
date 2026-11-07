# Finnip

Asistente personal autoalojado. Recibe órdenes en lenguaje natural por
Telegram y controla dispositivos del hogar mediante Home Assistant.

## Arquitectura

```
Telegram → Hermes Agent (finnip-brain)
             └─ plugin finnip_lights ──HTTP + Bearer──► Home Bridge (finnip-home-bridge)
                                                          └─ REST ──► Home Assistant (finnip-homeassistant)
                                                                        └─ Bluetooth ──► light.leds_monitores
```

| Servicio | Contenedor | Función |
|---|---|---|
| `hermes` | `finnip-brain` | Agente de IA conectado a Telegram. Carga el plugin `finnip_lights`. |
| `home-bridge` | `finnip-home-bridge` | API TypeScript (Fastify + Zod). Único punto de acceso de Hermes a Home Assistant. |
| `homeassistant` | `finnip-homeassistant` | Domótica. Red del host y D-Bus para Bluetooth (integración `elkbledom`). |

Hermes nunca recibe `HA_TOKEN`: solo conoce `BRIDGE_API_KEY` y una lista
cerrada de operaciones expuestas por Home Bridge.

## Estructura

```
apps/
  home-bridge/     API TypeScript, pruebas Vitest y Dockerfile (ver su README)
  finnip-lights/   Plugin Python de Hermes: herramienta finnip_lights
compose/
  compose.yaml     Definición de los tres servicios
config/            Variables de entorno con secretos (no versionado)
data/              Datos persistentes de Hermes y Home Assistant (no versionado)
backups/           Respaldos locales (no versionado)
```

## Configuración

Crear con permisos `600`:

- `config/homeassistant.env`: `HA_TOKEN` y `BRIDGE_API_KEY` (mínimo 32 caracteres).
- `config/hermes-bridge.env`: `BRIDGE_API_KEY`, con el mismo valor.

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

Para actualizar el plugin:

```sh
sudo cp apps/finnip-lights/*.py apps/finnip-lights/plugin.yaml data/hermes/plugins/finnip-lights/
sudo docker compose restart hermes
```

## Home Bridge

Rutas autenticadas con `Authorization: Bearer <BRIDGE_API_KEY>`:

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/health` | Estado del servicio (público) |
| `GET` | `/lights/monitores` | Estado, brillo en % y RGB |
| `POST` | `/lights/monitores/on` | Encender y confirmar estado |
| `POST` | `/lights/monitores/off` | Apagar y confirmar estado |
| `POST` | `/lights/monitores/color` | `{ "rgb": [r, g, b], "brightness": 1-100 }` |

Las órdenes devuelven `confirmed` y `actual` con el estado que reporta Home
Assistant después de ejecutarlas. La imagen Docker solo se construye si pasan
la comprobación de tipos y las pruebas.
