# Finnip Home Bridge

API que expone a Finnip solo los dispositivos de Home Assistant marcados con la
etiqueta `finnip`, con autenticación mediante Bearer token.

## Estructura

- `src/index.ts`: arranque y escucha HTTP.
- `src/app.ts`: construcción de Fastify y conexión de dependencias.
- `src/devices.ts`: etiqueta, dominios permitidos y capacidades por dominio.
- `src/actions.ts`: acciones disponibles, su validación y su confirmación.
- `src/routes/`: métodos y rutas HTTP.
- `src/controllers/`: validación de entradas y respuestas HTTP.
- `src/services/`: cliente Home Assistant y descubrimiento de dispositivos.
- `src/schemas/`: configuración validada con Zod.
- `src/hooks/`: autenticación.
- `src/utils/`: comparación de colores RGB normalizados.
- `tests/`: pruebas Vitest con un Home Assistant simulado (`tests/fake-ha.ts`).

## Desarrollo y verificación

Requiere Node.js >=22.12.0 y npm. Las variables `HA_URL`, `HA_TOKEN` y
`BRIDGE_API_KEY` (mínimo 32 caracteres) deben estar en el entorno al iniciar
el servicio. Las pruebas usan valores ficticios y no necesitan credenciales.

```sh
npm ci
npm run typecheck
npm test
npm run build
```

`npm run test:watch` ejecuta Vitest en modo interactivo. El Dockerfile también
comprueba tipos y ejecuta pruebas antes de compilar; la imagen final contiene
solo las dependencias de producción y el código compilado.

## Agregar un dispositivo

No requiere cambiar código ni desplegar:

1. Agrega el dispositivo a Home Assistant.
2. En Home Assistant, ponle la etiqueta `finnip` a su entidad.
3. Finnip lo verá en su siguiente `GET /devices`.

También se puede pedir a Finnip ("agrega la lámpara del buró"): usa
`GET /candidates` y `POST /devices/:id/expose`, y confirma antes de exponer.

Solo se exponen entidades con la etiqueta **y** de un dominio permitido:
`light`, `switch`, `cover` y `climate`. Una entidad etiquetada de otro dominio
(`lock`, `alarm_control_panel`…) se ignora. Para permitir un dominio nuevo hay
que añadirlo en `src/devices.ts` con sus capacidades y pruebas.

El id de cada dispositivo es su `entity_id` y el nombre es su `friendly_name`.

## Capacidades

Se calculan con los atributos que reporta Home Assistant:

| Dominio | Capacidad | Origen |
|---|---|---|
| `switch` | `on`, `off` | siempre |
| `light` | `on`, `off` | siempre |
| `light` | `brightness` | algún `supported_color_modes` distinto de `onoff` |
| `light` | `color` | `supported_color_modes` incluye `hs`, `rgb`, `rgbw`, `rgbww` o `xy` |
| `light` | `color_temp` | `supported_color_modes` incluye `color_temp`; respeta `min_color_temp_kelvin`/`max_color_temp_kelvin` |
| `cover` | `open`, `close`, `position`, `stop` | bits 1, 2, 4 y 8 de `supported_features` |
| `climate` | `temperature` | bit 1 de `supported_features`; respeta `min_temp`/`max_temp` |
| `climate` | `hvac_mode` | `hvac_modes` no vacío; solo acepta esos modos |

## Rutas

| Método | Ruta | Cuerpo |
|---|---|---|
| `GET` | `/devices` | — |
| `GET` | `/devices/:id` | — |
| `POST` | `/devices/:id/on` · `off` · `open` · `close` · `stop` | — |
| `POST` | `/devices/:id/brightness` | `{ "brightness": 1-100 }` |
| `POST` | `/devices/:id/color` | `{ "rgb": [r, g, b], "brightness": 1-100 }` |
| `POST` | `/devices/:id/color_temp` | `{ "kelvin": 1000-12000, "brightness": 1-100 }` |
| `POST` | `/devices/:id/position` | `{ "position": 0-100 }` |
| `POST` | `/devices/:id/temperature` | `{ "temperature": n }` |
| `POST` | `/devices/:id/hvac_mode` | `{ "hvac_mode": "cool" }` |

Respuestas de error: `404` si el dispositivo no está expuesto o la acción no
existe; `400` si el cuerpo es inválido, la acción no está en `capabilities` o
el valor está fuera de los límites del dispositivo; `502` si Home Assistant
falla. Las entradas se validan antes de contactar a Home Assistant.

## Exponer dispositivos y modos
| Método | Ruta | Cuerpo |
|---|---|---|
| `GET` | `/candidates` | — |
| `POST` | `/devices/:id/expose` · `hide` | — |
| `GET` | `/modes` | — |
| `GET` | `/modes/:slug` | — |
| `PUT` | `/modes/:slug` | `{ "name": "lectura", "music": false, "steps": [{ "device": "light.lampara", "action": "color_temp", "params": { "kelvin": 2700 } }] }` |
| `DELETE` | `/modes/:slug` | — |

Límites, aplicados aquí y no en el modelo:
- Solo se exponen u ocultan `light`, `switch`, `cover`, `climate` y
  `media_player`. Nunca cerraduras, alarmas ni cámaras.
- Un modo es siempre el script `modo_<slug>`, con `slug` `^[a-z0-9_]{1,40}$`.
  Ninguna ruta toca otros scripts.
- Cada paso es una acción de estado (`on`, `off`, `brightness`, `color`,
  `color_temp`, `open`, `close`, `stop`, `position`, `temperature`,
  `hvac_mode`, `pause`, `resume`, `volume`) sobre un dispositivo expuesto, y
  se valida igual que una orden directa. Un paso inválido rechaza el modo
  completo (`400`, "Paso N …").
- Un modo con pasos editados a mano en Home Assistant (esperas, condiciones,
  otros servicios) se lee con `editable: false` y `PUT` responde `409`.
- La música va en la descripción del script: `Finnip: con música` o
  `Finnip: sin música`. Sin descripción vale "con música". `GET /devices`
  la devuelve como `music` en los dispositivos `script`.
- `hide` responde `used_by_modes` con los modos que aún usan el dispositivo.

Las etiquetas se cambian por WebSocket (`config/entity_registry/*`) y los
modos con la API del editor de scripts (`/api/config/script/config/<id>`).
Ambas requieren que `HA_TOKEN` sea de un usuario **administrador**. Una entidad
sin entrada en el registro no admite etiquetas (`404`).

Home Bridge no publica puertos; se prueba desde un contenedor de la red de
Compose (por ejemplo `finnip-brain`):

```sh
curl -s -H "Authorization: Bearer $BRIDGE_API_KEY" http://home-bridge:3000/candidates
curl -s -H "Authorization: Bearer $BRIDGE_API_KEY" http://home-bridge:3000/modes
```

## Comportamiento

`GET /health` es público; el resto requiere autenticación. `GET /lights/monitores`
y `POST /lights/monitores/:action` se mantienen para versiones anteriores del
plugin y equivalen a `light.leds_monitores`; también requieren la etiqueta.

Cada acción lee el estado después de ejecutarse y devuelve `actual` con lo que
reporta Home Assistant y `confirmed` si coincide con lo pedido. `requested` se
incluye cuando la acción lleva datos. La confirmación de color comprueba
encendido, brillo y RGB proporcional, con tolerancia de un paso por canal.
`confirmed: false` justo después de una orden puede deberse a dispositivos
lentos (Bluetooth), no necesariamente a un fallo.

Las pruebas usan `Fastify.inject()` y un cliente HTTP simulado: no abren puertos
ni modifican dispositivos reales. Cubren autenticación, descubrimiento por
etiqueta, capacidades por dominio, validación, confirmación y fallos de Home
Assistant.

Referencias: [Fastify testing](https://fastify.dev/docs/latest/Guides/Testing/)
y [Vitest](https://vitest.dev/guide/).

## Activación en el servidor

Solo cuando se decida desplegar:

```sh
cd /srv/finnip/compose
sudo docker compose up -d --build home-bridge
```
