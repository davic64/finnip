# Spec Delta

## ADDED Requirements

### Requirement: Señalar con el mouse
Cuando el usuario se refiere a algo en pantalla ("esto", "aquí"), la tarea SHALL ir con una captura de la zona alrededor del puntero del mouse, tomada en la Mac, sin el holograma de Finnip encima. Claude Code SHALL recibir la captura y la posición del puntero en ella, tanto para proyectos en la Mac como en la nube. La captura MUST NOT entrar al historial de git del proyecto.

#### Scenario: Agrandar un botón
- **WHEN** el usuario apunta a un botón de su app y dice "Finnip, en tienda, haz esto más grande"
- **THEN** Claude Code ve la captura con el puntero sobre el botón y agranda ese botón
