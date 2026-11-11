# Tasks

## 1. App de escritorio (Rust)
- [x] 1.1 Módulo `projects.rs`: `list`, `create` (git init o `gh repo clone`), `open` (Zed), `task` (Claude Code en hilo, con sesiones por proyecto), `run`/`stop` y `status`. Validación de nombres, repositorios y comandos permitidos, con pruebas.
- [x] 1.2 Comando `project` permitido a la página remota y hook `projectDone`.

## 2. App web y gateway
- [x] 2.1 Página (escritorio): `project_request` → `invoke("project")` → `project_result`; `projectDone` → `project_done`.
- [x] 2.2 Gateway: `POST /internal/project` con espera de resultado, y `project_done` como turno de Hermes en el último dispositivo usado. Con pruebas.

## 3. Hermes
- [x] 3.1 Plugin `finnip-projects` con la herramienta `finnip_projects` y su esquema. Desplegarlo y habilitarlo en `config.yaml`.

## 4. Nube
- [x] 4.1 `apps/finnip-runner` (systemd): las mismas acciones en `/srv/projects`, la vista previa en el puerto 4100 detrás de `dev.finnip` en Caddy, y el aviso de tarea terminada al gateway. Con pruebas.
- [x] 4.2 Modo bypass con `CONFIRMAR:` y bloqueos en la Mac y en la nube; "abre en la nube" con Zed por SSH.

## 5. Prueba real
- [ ] 5.1 Por voz: crear un proyecto, pedir una página, autorizar `npm install`, correrlo y verlo en el navegador.
