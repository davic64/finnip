# Spec Delta

## MODIFIED Requirements

### Requirement: Escena central con fondo oscurecido
Cuando Finnip muestra el estado del servidor o la agenda, la app SHALL llevar el holograma y el panel al centro y oscurecer el resto de la pantalla con una capa semitransparente. La escena MUST terminar sola cuando el panel se oculta. Un panel pedido desde otro dispositivo SHALL ocultarse solo, aunque la Mac no esté en conversación.

#### Scenario: Estado del servidor
- **WHEN** el usuario pregunta "¿cómo está el servidor?"
- **THEN** el fondo se oscurece, aparecen al centro las métricas y el holograma, y al ocultarse el panel la pantalla vuelve a la normalidad

#### Scenario: Agenda
- **WHEN** el usuario pregunta "¿qué tengo esta semana?"
- **THEN** la agenda aparece al centro sobre el fondo oscurecido mientras Finnip la lee

#### Scenario: Pedido desde el celular
- **WHEN** el usuario le pregunta al celular "¿cómo está el servidor?"
- **THEN** las métricas aparecen al centro de la Mac y se ocultan solas al terminar

### Requirement: Controles de barra de menú, atajo y arranque
La app SHALL tener un ícono en la barra de menú con:
- mostrar u ocultar Finnip;
- activar o desactivar la escucha («Escuchar «Finnip»»);
- elegir la pantalla;
- abrir Preferencias;
- salir.

La escucha SHALL recordarse al reiniciar la app. Un atajo de teclado global (⌥⌘F por defecto, personalizable) SHALL despertar a Finnip para hablar sin decir su nombre, o silenciarlo si ya escucha. Con la escucha desactivada, el atajo SHALL abrir el micrófono para una sola frase y cerrarlo al terminar, sin reactivar la escucha. La app SHALL iniciarse sola al abrir sesión, con opción para desactivarlo.

#### Scenario: Desactivar la escucha
- **WHEN** el usuario desmarca "Escuchar «Finnip»" en el menú
- **THEN** la app cierra el micrófono, no reacciona a "Finnip", el ícono muestra que no escucha, y sigue así tras reiniciar la app

#### Scenario: Hablar con el atajo
- **WHEN** el usuario presiona el atajo global con Finnip en reposo
- **THEN** el holograma aparece escuchando y la siguiente frase se atiende sin decir "Finnip"

#### Scenario: Atajo con la escucha desactivada
- **WHEN** el usuario presiona el atajo con la escucha desactivada y hace una pregunta
- **THEN** Finnip responde y, al volver al reposo, el micrófono se cierra otra vez
