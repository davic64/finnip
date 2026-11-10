# Proposal

## Why

Hoy, para que Finnip controle un dispositivo nuevo hay que entrar a Home Assistant y ponerle a mano la etiqueta `finnip`. Para crear o cambiar un modo (Modo estudio, Modo cine…) hay que editar scripts en Home Assistant. El usuario quiere hacer las dos cosas hablando con Finnip ("agregué una lámpara nueva", "crea un modo lectura", "cambia el modo estudio"), sin darle a Finnip acceso total a su casa.

## What Changes

- **Dispositivos nuevos:**
  - Finnip puede listar los dispositivos de Home Assistant que todavía no controla, solo de los tipos permitidos (luces, enchufes, persianas, clima y bocinas).
  - Al confirmarlo el usuario, Finnip les pone la etiqueta `finnip`. También puede quitársela ("ya no controles el ventilador").
  - Nunca expone cerraduras, alarmas, cámaras ni ningún otro tipo.
- **Modos:**
  - Finnip puede crear, consultar, cambiar y borrar modos. Cada modo es un script `script.modo_*` de Home Assistant, etiquetado `finnip`.
  - Cada paso de un modo usa solo dispositivos que Finnip ya controla, y solo las acciones que Home Bridge ya valida para ellos.
  - Un modo indica si lleva música elegida por Finnip o no. Esto reemplaza la lista fija de modos sin música (`QUIET_MODES`).
  - Finnip no sobrescribe un modo editado a mano en Home Assistant que tenga pasos que no entiende.
- **Temperatura de color:** nueva acción `color_temp` (Kelvin) para luces que la soportan. La usa el Modo cálido y también sirve para pedir "pon la lámpara en blanco cálido".
- **Home Bridge** sigue siendo el único que tiene el token de Home Assistant. Las nuevas rutas validan todo antes de llamar a Home Assistant.
- **Plugin `finnip-lights`:** acciones nuevas para el modelo, y el aviso de música del modo se lee del propio modo.
- **Confirmación:** Finnip confirma con el usuario antes de exponer un dispositivo y antes de borrar un modo.
- **Fuera de alcance:** automatizaciones, escenas, editar dispositivos o integraciones, y cualquier dominio fuera de la lista permitida.

## Capabilities

### New Capabilities

- `device-exposure`: descubrir dispositivos de Home Assistant que Finnip aún no controla, dentro de los tipos permitidos, y exponerlos u ocultarlos con la etiqueta `finnip`.
- `home-modes`: crear, consultar, cambiar, borrar y activar modos (scripts `modo_*`) hechos de pasos sobre dispositivos expuestos, con su indicación de música.

### Modified Capabilities

## Impact

- **Home Bridge (`apps/home-bridge`):**
  - Rutas nuevas para candidatos, exponer y ocultar dispositivos, y para listar, leer, guardar y borrar modos.
  - Cliente WebSocket mínimo para el registro de entidades de Home Assistant, porque las etiquetas no tienen API REST.
  - Acción `color_temp`.
  - El script expone su indicación de música.
  - Pruebas con vitest.
- **Plugin `finnip-lights`:** acciones nuevas en el esquema de la herramienta. La ruta rápida de modos lee la música del modo y desaparece `QUIET_MODES`. Pruebas con unittest.
- **Home Assistant:** los scripts se guardan con la API de configuración de Home Assistant, en `scripts.yaml`. No hay modos que migrar: el usuario borró los cuatro anteriores.
- **Hermes:** una regla en `SOUL.md`, que es configuración fuera del repo: confirmar antes de exponer y antes de borrar.
- **Sin cambios** en `compose.yaml`, secretos ni el voice gateway.
