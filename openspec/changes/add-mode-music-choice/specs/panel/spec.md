## ADDED Requirements
### Requirement: Música elegida en modos y rutinas
El panel SHALL permitir elegir para un modo "Finnip la elige", "Sin música" o una canción, artista o playlist concreta, opcionalmente con artistas similares; y para una rutina, sin música o una concreta.
#### Scenario: Modo con artista y similares
- **WHEN** el usuario guarda un modo con el artista "Coldplay" y "y artistas similares"
- **THEN** al activarlo, Finnip reproduce "la estación de Coldplay" en la Echo sin elegir otra música
### Requirement: Ajustes de dispositivo en pasos
Modos y rutinas SHALL poder elegir una opción de una entidad `select` y fijar el valor de una entidad `number` expuestas a Finnip, dentro de sus opciones y rango.
#### Scenario: Leds con audio
- **WHEN** un modo enciende "Monitores Sincronía de audio" y elige el efecto `mic_spectrum`
- **THEN** los leds de los monitores reaccionan al audio con ese efecto
