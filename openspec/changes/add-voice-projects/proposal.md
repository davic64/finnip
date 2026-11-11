# Proposal

## Why
El usuario quiere construir software hablando con Finnip: empezar un proyecto o retomar uno de sus repositorios, pedir cambios, verlo correr en su Mac, y que Finnip abra el editor, todo por voz. Programar lo hace mejor un agente especializado (Claude Code, que ya tiene en la Mac con sesión iniciada) que el modelo de conversación de Finnip. Finnip pone la voz y el puente.

## What Changes
- **Proyectos en la Mac (fase 1, este cambio):**
  - "Finnip, nuevo proyecto X" crea `~/Projects/x` con git. "Retoma el repositorio Y" lo clona con `gh`. "Abre X" lo abre en Zed.
  - "Agrégale…": Finnip le pasa la orden a Claude Code en ese proyecto, sin pantalla (`claude -p`). La sesión continúa entre órdenes. Al terminar, Finnip resume por voz qué hizo.
  - Permisos: Claude Code corre en modo bypass y no pide permiso para editar, instalar dependencias ni correr comandos. Antes de algo importante (borrar lo que no creó, `git push`, reescribir historial, publicar, pagar, credenciales) se detiene con una línea `CONFIRMAR:`, y Finnip le pregunta al usuario. Como red de seguridad, `git push`, `git reset --hard`, `sudo` y `npm publish` quedan bloqueados hasta que el usuario confirma.
  - También proyectos que ya están en `~/Documents`: abrir, programar, correr y detener, con su ruta, o con "busca la carpeta X". Nada fuera de `~/Projects` y `~/Documents`.
  - "Elimina el proyecto X", en la Mac o en la nube, pide confirmación y lo manda a la papelera: `~/.Trash` en la Mac, `/srv/projects/.trash` en el servidor. Solo proyectos de `~/Projects` o de la nube.
  - "Córrelo" levanta el servidor de desarrollo del proyecto (`dev` o `start` de package.json, o `cargo run`) y abre la página en el navegador. "Detenlo" lo para.
  - La app de escritorio solo acepta esas acciones, solo dentro de `~/Projects`, y nunca recibe comandos de shell del servidor.
- **En la nube (fase 2, este cambio):**
  - "En la nube" hace lo mismo en `/srv/projects` del servidor, con `apps/finnip-runner`, un servicio de systemd que corre con el usuario que inició sesión en Claude Code.
  - Cada proyecto corriendo tiene su vista previa en `http://<proyecto>.dev.finnip`, y pueden correr varios a la vez. El servicio le da un puerto libre (4101-4199) y le agrega la ruta a Caddy por su API de administración local.
  - "Abre X en la nube" lo abre en Zed de la Mac por SSH.
  - Clona con `git` sobre HTTPS; con `gh auth login` en el servidor también funcionan los repositorios privados.
- **Señalar en pantalla (fase 3, otro cambio):** "cambia esto" con una captura de la app y lo que está bajo el puntero.

## Capabilities

### New Capabilities
- `voice-projects`: crear, retomar, abrir, programar con Claude Code, correr y detener proyectos locales por voz.
