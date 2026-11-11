# Spec Delta

## ADDED Requirements

### Requirement: Solo la voz del usuario
Con una huella de voz guardada, el voice gateway SHALL ignorar toda frase de 1 s o más cuya voz no coincida con la del usuario, y MUST NOT mandarla a Hermes. Sin huella guardada, SHALL atender las frases como antes.

#### Scenario: Alexa habla mientras Finnip escucha
- **WHEN** Alexa responde algo justo después de una respuesta de Finnip
- **THEN** Finnip lo ignora y vuelve a esperar

#### Scenario: El usuario contesta
- **WHEN** el usuario contesta la pregunta de Finnip
- **THEN** la frase llega a Hermes como siempre

### Requirement: Registrar la voz leyendo frases
"Finnip, aprende mi voz" SHALL mostrar en el dispositivo con el que se habla cinco frases, una a la vez, y pasar a la siguiente cuando el usuario lee la actual. Al terminar, SHALL guardar la huella y confirmarlo con voz. "Cancela" SHALL interrumpir el proceso sin guardar nada.

#### Scenario: Registro completo
- **WHEN** el usuario dice "Finnip, aprende mi voz" y lee las cinco frases
- **THEN** cada frase aparece al terminar la anterior, y al final Finnip dice "Listo, señor. Ya reconozco su voz."
