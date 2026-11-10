# Tasks

## 1. Temperatura de color

- [x] 1.1 Agregar la acción `color_temp` en `apps/home-bridge/src/actions.ts`: entrada `{kelvin, brightness?}`, `check` contra `min_color_temp_kelvin` y `max_color_temp_kelvin`, `confirm` a ±100 K. Agregar la capability para luces con `color_temp` en `supported_color_modes` (`devices.ts`), y `color_temp_kelvin` con su rango en `Device`. Verificar con pruebas vitest: blanco cálido confirmado, fuera de rango rechazado, y una luz sin `color_temp` que no ofrece la acción.

## 2. Registro de Home Assistant (etiquetas) y configuración de scripts

- [x] 2.1 Crear `apps/home-bridge/src/services/registry.ts`, un cliente WebSocket mínimo (Node 22) con `getLabels(entityId)` y `setLabels(entityId, labels)` (autenticar, un comando, timeout de 5 s, cerrar), inyectable en el servicio. Verificar con una prueba vitest contra un servidor WebSocket falso: autenticación, comando y error de Home Assistant.
- [x] 2.2 Agregar al servicio de Home Assistant `getScriptConfig`, `saveScriptConfig` y `deleteScriptConfig` (`/api/config/script/config/<id>`), y simular esa API en `tests/fake-ha.ts`. Verificar con pruebas vitest de ida y vuelta.

## 3. Exponer y ocultar dispositivos

- [x] 3.1 Agregar `GET /candidates`: entidades sin `finnip` de los dominios exponibles (permitidos menos `script`), con id, nombre, dominio y estado. Verificar con vitest: una cerradura y una entidad ya etiquetada no aparecen.
- [x] 3.2 Agregar `POST /devices/:id/expose` y `POST /devices/:id/hide`, que conservan las otras etiquetas, rechazan dominios no permitidos o ids mal formados sin llamar a Home Assistant, dan un error claro si la entidad no está en el registro, y en `hide` devuelven los modos que usan el dispositivo. Verificar con vitest los escenarios de la spec `device-exposure`.

## 4. Modos

- [x] 4.1 Agregar `fromData` a las acciones permitidas en modos y las funciones que traducen paso a paso de Home Assistant y de vuelta, más `editable`. Verificar con vitest, usando como datos de prueba los cuatro modos anteriores (del respaldo de `scripts.yaml`), que se leen como `editable: true` y producen el mismo YAML al guardarse, y que un paso desconocido da `editable: false`.
- [x] 4.2 Agregar `GET /modes`, `GET /modes/:slug`, `PUT /modes/:slug` y `DELETE /modes/:slug`, con slug validado, solo `modo_*`, validación de cada paso con el esquema y el `check` de su acción contra el dispositivo expuesto, rechazo del modo completo indicando el paso inválido, protección de modos no editables, descripción con la música, y etiqueta `finnip` tras crear (con reintento). Verificar con vitest los escenarios de la spec `home-modes`.
- [x] 4.3 Agregar `music` a los dispositivos `script` de `GET /devices`, leído de la descripción. Verificar con vitest: "sin música" da `false`, y sin descripción da `true`.
- [x] 4.4 Documentar en `apps/home-bridge/README.md` las rutas nuevas, los límites (dominios, `modo_*`, acciones permitidas en modos) y el requisito del token de administrador. Verificar que los ejemplos `curl` del README funcionen contra el servidor.

## 5. Plugin y Hermes

- [x] 5.1 Agregar a `finnip_lights` las acciones `discover`, `expose`, `hide`, `modes`, `mode`, `save_mode` y `delete_mode`, con el nombre del modo convertido a slug y la descripción de la herramienta que pide confirmar antes de `expose` y `delete_mode`. Verificar con unittest y un Home Bridge falso.
- [x] 5.2 Hacer que la ruta rápida de modos lea `music` del script y quitar `QUIET_MODES`. Verificar con unittest: un modo sin música no pide música al modelo y uno con música sí.

## 6. Migración y despliegue

- [ ] 6.1 Desplegar Home Bridge y el plugin, agregar la regla de confirmación a `SOUL.md` y reiniciar Hermes. Verificar con `GET /health` y `GET /modes` (lista vacía).

## 7. Verificación integral

- [ ] 7.1 Recorrer con el usuario, por voz o Telegram:
  - Agregar un dispositivo nuevo con confirmación.
  - Ocultarlo.
  - Crear "modo lectura" con `color_temp` y activarlo.
  - Cambiar el brillo de un paso del Modo estudio.
  - Crear un modo sin música.
  - Borrar un modo con confirmación.
  - Intentar exponer una cerradura, que debe rechazarse.

  Anotar los resultados en el PR.

## Workflow follow-up

- Abrir un PR con el cambio. El usuario hace el merge.
- Archivar el cambio en OpenSpec después del merge.
