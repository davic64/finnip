# Finnip Home Bridge

API limitada a los dispositivos del catálogo, con autenticación mediante Bearer token.

## Estructura

- `src/index.ts`: arranque y escucha HTTP.
- `src/app.ts`: construcción de Fastify y conexión de dependencias.
- `src/devices.ts`: catálogo de dispositivos expuestos.
- `src/routes/`: métodos y rutas HTTP.
- `src/controllers/`: validación de entradas y respuestas HTTP.
- `src/services/`: cliente Home Assistant y operaciones de dispositivos.
- `src/schemas/`: contratos Zod y tipos derivados.
- `src/hooks/`: autenticación.
- `src/utils/`: comparación de colores RGB normalizados.
- `tests/`: pruebas Vitest con Home Assistant simulado.

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

## Catálogo de dispositivos

Solo se controlan los dispositivos declarados en `src/devices.ts`. Para agregar
uno, añade una entrada con su `entity_id` real de Home Assistant:

```ts
deskLamp: { entityId: "light.lampara_escritorio", type: "light", name: "Lámpara" },
```

La clave (`deskLamp`) es el id de la URL. `type` debe coincidir con el dominio
del `entity_id` (`light` o `switch`); una prueba lo comprueba.

| Método | Ruta | Tipos |
|---|---|---|
| `GET` | `/devices/:id` | todos |
| `POST` | `/devices/:id/on` | todos |
| `POST` | `/devices/:id/off` | todos |
| `POST` | `/devices/:id/color` | `light` |

Un id fuera del catálogo responde `404`; `color` en un dispositivo que no es
`light` responde `400`. Los `switch` devuelven solo `name` y `state`.

## Comportamiento

`GET /health` es público; el resto requiere autenticación. Las rutas
`/lights/monitores`, `/lights/monitores/color`, `/lights/monitores/on` y
`/lights/monitores/off` se mantienen para el plugin `finnip_lights` y equivalen
a `/devices/monitorLeds`.

La confirmación de color comprueba encendido, brillo en porcentaje y RGB
proporcional, con tolerancia de un paso por canal al normalizar a 255. Conserva
el RGB reportado en `actual`; no lo sustituye por el solicitado. Encender y
apagar leen el estado después de la orden: añaden `actual` y `confirmed`
(`true` si Home Assistant reporta `on`/`off` según la acción) a los campos
anteriores. El brillo solo acepta enteros de 1 a 100.

Las pruebas usan `Fastify.inject()` y un cliente HTTP simulado: no abren puertos
ni modifican luces reales. Cubren autenticación, validación, contratos de rutas,
normalización de color, conversión de brillo y fallos de Home Assistant.

Referencias: [Fastify testing](https://fastify.dev/docs/latest/Guides/Testing/)
y [Vitest](https://vitest.dev/guide/).

## Activación en el servidor

Solo cuando se decida desplegar:

```sh
cd /srv/finnip/compose
sudo docker compose up -d --build home-bridge
```
