# Tasks

## 1. Voice gateway
- [x] 1.1 `voiceprint.py`: huella CAM++ con sherpa-onnx, puntaje coseno, guardado atómico. Prueba con el modelo real dentro de la imagen.
- [x] 1.2 Ignorar frases de otra voz cuando hay huella, con el puntaje en el log. Las frases de menos de 1 s pasan.
- [x] 1.3 "Aprende mi voz": cinco frases una a la vez y "cancela". Verificar con pruebas que nada llega a Hermes.
- [x] 1.4 Descargar el modelo en el Dockerfile, montar `data/voice` y definir `VOICEPRINT`.

## 2. App web
- [x] 2.1 Panel con la frase a leer, en el celular y en la Mac; la pantalla del celular no se atenúa mientras está abierto.

## 3. Prueba real
- [ ] 3.1 Registrar la voz desde el celular, probar con Alexa hablando y ajustar `VOICE_MATCH` con los puntajes del log.
