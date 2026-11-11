# Spec Delta

## ADDED Requirements

### Requirement: Proyectos locales por voz
Finnip SHALL crear proyectos nuevos en `~/Projects`, clonar repositorios del usuario, abrirlos en Zed, correrlos y detenerlos, por voz y a través de la app de escritorio. La app MUST NOT ejecutar nada fuera de esas acciones ni fuera de `~/Projects`.

#### Scenario: Proyecto nuevo
- **WHEN** el usuario dice "Finnip, nuevo proyecto tienda"
- **THEN** existe `~/Projects/tienda` con git y se abre en Zed

### Requirement: Programar con Claude Code
Las órdenes sobre un proyecto SHALL ir a Claude Code en ese proyecto, continuando su sesión anterior. Al terminar, Finnip SHALL resumir por voz lo que hizo. Claude Code SHALL editar archivos sin preguntar. Los comandos no autorizados MUST quedar pendientes hasta que el usuario los autorice por voz.

#### Scenario: Autorizar un comando
- **WHEN** Claude Code necesita `npm install` y el usuario responde "sí"
- **THEN** la tarea se reanuda con solo ese comando permitido
