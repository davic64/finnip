# Tasks

## 1. Paneles genéricos

- [ ] 1.1 En `voice-gateway`, reemplazar `stats` por el evento `panel` con un registro de paneles (detector, lector con límite de 1.5 s y nota para el prompt). Migrar el panel del servidor.
- [ ] 1.2 En la PWA, convertir `hud.ts` en renderizadores por `kind`, conservando el panel del servidor.
- [ ] 1.3 Tests `unittest`: detección, lector lento omitido, lector con error omitido y un máximo de 2 paneles.

## 2. Clima y calendario (Home Assistant)

- [ ] 2.1 El usuario agrega en HA las integraciones Met.no y Google Calendar (con sus credenciales OAuth de Google Cloud). Verificar las entidades `weather.*` y `calendar.*`.
- [ ] 2.2 `home-bridge`: `GET /weather`, `GET /calendar` y `POST /calendar/events`, con tests de vitest.
- [ ] 2.3 Paneles `weather` y `calendar` en el gateway y la PWA.
- [ ] 2.4 Herramientas de calendario en el plugin de Hermes (consultar y crear) y atajo de agenda.

## 3. Gmail

- [ ] 3.1 `tools/google_auth.py` (`gmail.readonly`). El usuario lo corre y autoriza, y el token queda en `config/` con modo 600.
- [ ] 3.2 Panel `mail`: no leídos de la bandeja principal, sin el cuerpo.

## 4. Cierre

- [ ] 4.1 Actualizar el README con la configuración de cada integración.
- [ ] 4.2 Pruebas por voz de cada panel y medición de la latencia agregada.
