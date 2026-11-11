# Spec Delta

## ADDED Requirements

### Requirement: Modos desde el panel
El panel SHALL listar los modos, y crear, editar y borrar modos eligiendo para cada paso un dispositivo y una acción con sus valores. Un modo editado a mano en Home Assistant SHALL mostrarse sin opción de editarlo.

#### Scenario: Modo nuevo
- **WHEN** el usuario crea "Modo fiesta" con la lámpara en morado al 60 % y lo guarda
- **THEN** "Finnip, modo fiesta" lo activa

### Requirement: Rutinas desde el panel
El panel SHALL editar rutinas con una frase, una respuesta exacta y, opcionalmente, acciones sobre dispositivos, música y un modo. Al decir "Finnip" seguido de la frase, Finnip SHALL ejecutar las acciones, activar el modo, poner la música y responder solo el texto de la rutina. Los cambios SHALL aplicar sin reiniciar nada.

#### Scenario: Rutina de llegada
- **WHEN** el usuario dice "Finnip, despierta, ya llegó papá"
- **THEN** suena la música de la rutina y Finnip responde exactamente "Bienvenido a casa, señor. ¿Qué vamos a hacer hoy?"
