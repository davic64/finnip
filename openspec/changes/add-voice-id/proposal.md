# Proposal

## Why
El micrófono del celular y el de la Mac oyen todo lo que suena en el cuarto. Cuando Alexa contesta algo justo después de una respuesta de Finnip, mientras Finnip todavía escucha sin pedir "Finnip", su voz llega a Hermes como si fuera del usuario. Lo mismo puede pasar con la tele o con otra persona.

## What Changes
- **Huella de voz:**
  - El voice gateway calcula la huella de cada frase con 3D-Speaker CAM++ (sherpa-onnx, 26 MB, en el servidor). Tarda unos 110 ms por cada 3 s de audio.
  - La compara con la huella guardada del usuario. Si no se parece, ignora la frase.
- **"Finnip, aprende mi voz":**
  - El dispositivo con el que se habla muestra cinco frases, una a la vez, y el usuario las lee en voz alta.
  - Con las cinco se guarda la huella en `data/voice/voiceprint.json`. "Cancela" interrumpe el proceso.
- **Excepciones:**
  - Sin huella guardada, todo pasa como antes.
  - Las frases de menos de 1 s ("sí", "para") no se comparan.
  - "Finnip, para" mientras habla sigue funcionando.
- **Fuera de alcance:** distinguir a varias personas de la casa, o tener permisos distintos por persona.

## Capabilities

### New Capabilities
- `voice-id`: reconocer la voz del usuario e ignorar frases de otras voces; registrar la voz leyendo cinco frases en pantalla.
