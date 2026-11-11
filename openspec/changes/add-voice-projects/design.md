# Design

## Flujo
`finnip_projects`, la herramienta de Hermes, hace `POST /internal/project` al voice gateway, con la llave interna de `PARTS_API_KEY`. El gateway lo pasa a la app de escritorio conectada (`project_request`) y espera su `project_result`, como con las fotos. La página manda la petición a Rust con el comando `project`, el único nuevo que se le permite a la página remota.

Las tareas de Claude Code tardan minutos:
1. Rust responde de inmediato `started` y corre `claude` en un hilo.
2. Al terminar, se lo pasa a la página (`finnipDesktop.projectDone`), y la página lo manda al gateway (`project_done`).
3. El gateway mete el resultado en la conversación de voz como un turno de Finnip, en el último dispositivo con el que habló el usuario. Así Hermes lo resume y conoce los comandos pendientes para autorizarlos después.

## Decisiones
- **Rust no recibe comandos, solo acciones fijas:** `list`, `create`, `open`, `task`, `run`, `stop`.
  - Los nombres de proyecto son slugs (`^[a-z0-9][a-z0-9_-]{0,59}$`).
  - Los repositorios son `dueño/nombre` o una URL `https://github.com/...`.
  - Lo confirmado por voz llega como `confirmed: true`, y solo quita los bloqueos de esa orden.
- **Sin shell:** se lanza `zsh -lc 'exec "$0" "$@"' programa args…`. El shell de login da el PATH del usuario (fnm, bun, `~/.local/bin`), y los argumentos nunca se interpretan como shell.
- **Claude Code** corre con `--output-format json --permission-mode bypassPermissions --setting-sources project` y `--disallowedTools` para `git push`, `git reset --hard`, `sudo` y `npm publish`; las reglas de bloqueo se respetan incluso en bypass, y se omiten con `confirmed`. Usa `--resume <session_id>` si el proyecto ya tiene sesión. Las sesiones se guardan por proyecto.
- **Nube:** el gateway pasa las acciones con `where: "cloud"` a `apps/finnip-runner` por un socket Unix en `data/runner`. Esa carpeta es `finnip:10000` con permisos 750, así que solo entra el gateway. Al terminar una tarea, el servicio avisa a `/internal/project_done`.
  - Un `--append-system-prompt` le pide terminar con un resumen breve en español.
  - Solo puede haber una tarea por proyecto a la vez.
- **Correr el proyecto:** el gestor de paquetes se elige por el lockfile (bun, pnpm, yarn o npm). Se espera la primera URL `http://localhost:<puerto>` o `127.0.0.1` en la salida, hasta 90 s, y se abre con `open`. Detener mata el grupo de procesos.

## Riesgos
- Lo que corre el proyecto (`npm run dev`) es código del propio proyecto. → Solo proyectos de `~/Projects`, y siempre lo pide el usuario.
- Una tarea larga deja a Finnip sin noticias por minutos. → El resultado llega solo, y "¿cómo va?" consulta el estado.
