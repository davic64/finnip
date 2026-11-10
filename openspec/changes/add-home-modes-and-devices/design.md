# Design

## Context

- Home Bridge (`apps/home-bridge`, Fastify, Zod) es el único con el token de Home Assistant. Solo ve las entidades con la etiqueta `finnip` de los dominios permitidos (`ALLOWED_DOMAINS`). Lee las etiquetas con la API de plantillas (`label_entities`), porque `/api/states` no las trae.
- Cada acción de un dispositivo está definida una sola vez en `actions.ts`: esquema Zod de entrada, servicio de Home Assistant, `data(input)`, `check` y `confirm`. Los cuatro modos que había (borrados por el usuario, respaldo en `scripts.yaml.bak-20261109-before-delete-modes`) seguían esa forma: `light.turn_on` con `rgb_color` o `color_temp_kelvin` y `brightness_pct`, `media_player.volume_set` o `media_pause`, con `continue_on_error`. Sirven como datos de prueba del formato.
- El plugin `finnip-lights` activa los modos por la ruta rápida y decide la música con una lista fija, `QUIET_MODES = {"modo cine"}`.
- En Home Assistant 2026.11 las etiquetas solo se cambian por WebSocket (`config/entity_registry/*`). Los scripts sí tienen API REST de configuración, `/api/config/script/config/<id>`, que es la misma que usa el editor de Home Assistant: escribe `scripts.yaml` y recarga.

## Goals / Non-Goals

**Goals:**
- Exponer, ocultar y manejar modos sin salir de la conversación.
- Que Home Bridge siga siendo la frontera: todo se valida ahí con las mismas definiciones de acciones que ya usa el control directo.

**Non-Goals:**
- Automatizaciones, escenas, esperas o condiciones dentro de un modo.
- Renombrar dispositivos.
- Exponer dominios nuevos.
- Varias instancias de Home Assistant.

## Decisions

### Un paso de modo = una acción de Home Bridge
Un paso es `{device, action, params}`. Para guardarlo, Home Bridge busca la acción en `actions.ts`, valida `params` con su esquema y su `check` contra el estado real del dispositivo, y genera el paso de Home Assistant: `{action: "<dominio>.<servicio>", target: {entity_id}, data: def.data(params), continue_on_error: true}`.
- `continue_on_error` hace que un dispositivo desconectado no aborte todo el modo.
- En los modos solo se permiten acciones de estado: `on`, `off`, `brightness`, `color`, `color_temp`, `open`, `close`, `stop`, `position`, `temperature`, `hvac_mode`, `pause`, `resume` y `volume`.
- Se excluyen `play`, porque la música la elige Finnip al activar el modo; `command`, porque es texto libre para Alexa; y `run`, porque no se anidan modos.
- *Alternativa: aceptar el YAML de Home Assistant que escriba el modelo.* Abriría cualquier servicio de Home Assistant. Se descarta.

### Leer un modo = invertir la traducción
Cada acción permitida en modos gana `fromData(service, data)`, que devuelve sus `params` o `undefined`. Por ejemplo, `turn_on` con `color_temp_kelvin` y `brightness_pct` se lee como `color_temp`. Al leer un modo, cada paso se intenta traducir. Si alguno no se puede, el modo se marca `editable: false` y la ruta de guardado rechaza sobrescribirlo. Así se protegen las ediciones hechas a mano en Home Assistant.

### La música del modo, en la descripción del script
El campo `description` del script lleva `Finnip: con música` o `Finnip: sin música`. Se lee en Home Assistant y no necesita campos propios. Sin descripción reconocible, vale "con música".
- Home Bridge agrega `music: boolean` a los dispositivos `script`, leyendo la configuración de cada script expuesto. Son pocos, y es una llamada local por script en `GET /devices`.
- El plugin usa ese campo en lugar de `QUIET_MODES`.

### Rutas nuevas en Home Bridge

| Ruta | Qué hace |
|---|---|
| `GET /candidates` | Entidades sin etiqueta de dominios exponibles (los permitidos menos `script`), con id, nombre, dominio y estado |
| `POST /devices/:id/expose` | Agrega la etiqueta `finnip` |
| `POST /devices/:id/hide` | Quita la etiqueta `finnip` |
| `GET /modes` | Lista los modos |
| `GET /modes/:slug` | Pasos, música, `editable` |
| `PUT /modes/:slug` | Crea o reemplaza: `{name, music, steps}` |
| `DELETE /modes/:slug` | Borra el modo |

- `slug` sigue `^[a-z0-9_]{1,40}$`, y el id del script es siempre `modo_<slug>`. Ninguna ruta acepta otro script.
- Al exponer u ocultar se conservan las demás etiquetas de la entidad. Para eso se leen con `config/entity_registry/get` antes de actualizar.
- Una entidad sin entrada en el registro no puede llevar etiquetas. En ese caso se devuelve un error claro.
- Ocultar responde también qué modos usan ese dispositivo, para que Finnip lo avise.
- Después de `PUT`, la etiqueta `finnip` se pone al script nuevo. El registro lo crea Home Assistant al recargar, así que se reintenta unas veces en 2 s como máximo.

### Cliente WebSocket mínimo
`registry.ts` usa el `WebSocket` global de Node 22. Abre, autentica con el mismo token, envía un comando, espera su resultado (timeout de 5 s) y cierra. Se usa solo para etiquetas, que son poco frecuentes.
- Se inyecta en el servicio, igual que `fetchImpl`, para que las pruebas usen un registro falso.
- *Alternativa: dejar el WebSocket abierto todo el tiempo.* Implica reconexión y estado para algo que pasa pocas veces. Se descarta.

### `color_temp`
- Nueva acción para luces con `color_temp` entre sus `supported_color_modes`.
- Entrada: `{kelvin, brightness?}`, validada contra `min_color_temp_kelvin` y `max_color_temp_kelvin`.
- Datos: `color_temp_kelvin` y `brightness_pct`.
- Se confirma cuando el `color_temp_kelvin` reportado está a ±100 K.
- `COLOR_MODES` no cambia.

### Confirmación del usuario
La exige `SOUL.md` y la descripción de la herramienta: "nombra el dispositivo o el modo y espera un sí antes de `expose` o `delete_mode`". Home Bridge no puede verificar que hubo confirmación. Lo que sí garantiza es el límite: nada fuera de los dominios permitidos ni de `modo_*`.

## Risks / Trade-offs

- [El modelo expone un dispositivo o borra un modo sin preguntar] → Es una regla en SOUL y en la herramienta. El daño posible está acotado: solo dominios permitidos y solo `modo_*`. Ocultar y recrear es reversible.
- [La API de configuración de scripts no es pública ni estable] → Es la que usa el propio editor de Home Assistant. Si cambia, fallan las pruebas contra la versión real (tarea de verificación) y el resto de Finnip sigue funcionando.
- [El token de Home Bridge debe ser de un usuario administrador para usar la API de configuración] → Ya lo es, porque lee plantillas y llama servicios. Se documenta. El límite real lo pone Home Bridge, no el token.
- [`PUT` sobre un modo editado a mano lo perdería] → `editable: false` lo impide. Guardar exige que el modo no exista o que todos sus pasos se puedan traducir.
- [Varias llamadas extra en `GET /devices`, una por script] → Son pocas y locales. Si crecen, se cachean (comentario `ponytail`).

## Migration Plan

1. Desplegar Home Bridge con las rutas nuevas y `color_temp`. Las rutas existentes no cambian.
2. Desplegar el plugin, que ahora lee `music` del modo, y la regla de SOUL. Reiniciar Hermes.
3. **Vuelta atrás:** las versiones anteriores de Home Bridge y del plugin siguen funcionando con los modos creados (son scripts normales). Solo se pierde el campo `music`, y vuelve `QUIET_MODES`.
