# Spec Delta

## ADDED Requirements

### Requirement: App Android siempre escuchando
La app Android SHALL cargar la app web de Finnip a pantalla completa y abrir el micrófono al arrancar, en reposo, esperando "Finnip". La app MUST NOT ofrecer un control para apagar el micrófono.

#### Scenario: Arranque
- **WHEN** el usuario abre la app por primera vez
- **THEN** Android pide permiso de micrófono una vez, y después Finnip queda en reposo esperando "Finnip"

#### Scenario: Sin conexión
- **WHEN** el celular no llega al servidor
- **THEN** la app lo vuelve a intentar sola hasta conectarse

### Requirement: Pantalla atenuada en reposo
La pantalla SHALL quedarse siempre encendida mientras la app está abierta. Tras 10 s en reposo, la app SHALL bajar el brillo de su ventana al mínimo. Al despertar Finnip, SHALL regresarlo al brillo normal.

#### Scenario: Conversación
- **WHEN** el usuario dice "Finnip, ¿qué hora es?" con la pantalla atenuada
- **THEN** el brillo sube mientras Finnip escucha y responde, y vuelve a bajar 10 s después

### Requirement: Modo kiosco
La app SHALL poder elegirse como pantalla de inicio del celular, y el botón atrás MUST NOT cerrarla.

#### Scenario: Reinicio del celular
- **WHEN** el celular se reinicia con Finnip como pantalla de inicio
- **THEN** Finnip arranca solo y queda escuchando

### Requirement: Paneles en la Mac
Si hay una app de escritorio conectada y la pregunta llega de otro dispositivo, el voice gateway SHALL mostrar el estado del servidor y la agenda en la app de escritorio, y no en ese dispositivo. Sin app de escritorio, el panel SHALL mostrarse en el dispositivo que preguntó.

#### Scenario: Estado del servidor desde el celular
- **WHEN** el usuario le pregunta al celular "¿cómo está el servidor?" con la Mac conectada
- **THEN** las métricas aparecen en la Mac, y el celular responde con voz
