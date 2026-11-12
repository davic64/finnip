# Proposal
## Why
Al crear un modo solo se podía marcar "Finnip elige música", y la música de una rutina era texto libre. El usuario quiere elegir la canción, el artista o la playlist exacta, con la opción de sumar artistas similares. También quiere que los leds de los monitores sigan el audio desde un modo o una rutina.
## What Changes
- **Música en modos:** `music` admite `true` (Finnip elige), `false` (sin música) o el texto exacto para Alexa. Se guarda en la descripción del script como `Finnip: música: <texto>`. Al activar el modo, `finnip-lights` reproduce ese texto en la Echo y el modelo no elige otra música.
- **Panel:** selector de música para modos y rutinas: canción, artista o playlist, con "y artistas similares". Los similares se piden con la estación de Apple Music ("la estación de X").
- **Ajustes de dispositivo:** Home Bridge acepta los dominios `select` (acción `option`) y `number` (acción `value`), validados contra las opciones y el rango de la entidad. Con eso, modos y rutinas pueden encender la sincronía de audio de los leds, elegir su efecto y fijar la sensibilidad del micrófono.
## Capabilities
### Modified Capabilities
- `panel`: música elegida y ajustes de dispositivo en modos y rutinas.
