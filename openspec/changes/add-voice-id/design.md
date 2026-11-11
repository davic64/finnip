# Design

## Decisions
- **Modelo:** CAM++ de 3D-Speaker, entrenado en chino e inglés con unos 200 000 hablantes, a través de sherpa-onnx.
  - La huella no depende del idioma, así que sirve para el español.
  - El modelo se descarga al construir la imagen, igual que Parakeet.
- **Comparación:** similitud coseno contra el promedio normalizado de las cinco huellas.
  - El umbral está en `VOICE_MATCH` (0.4 por defecto) y se ajusta con los puntajes del log del gateway.
- **Dónde se compara:**
  - Después de revisar la palabra "Finnip" y antes de mandar la frase a Hermes, así el ruido sin "Finnip" no gasta cómputo.
  - "Aprende mi voz" se atiende antes de comparar, para poder volver a registrarse si la huella sale mala.
- **Registro:**
  - Lo lleva la sesión del dispositivo que lo pidió.
  - Mientras dura, las frases de esa sesión no necesitan "Finnip" y nunca van a Hermes.
  - Las frases a leer no contienen "Finnip" ni órdenes, para que otro dispositivo que esté escuchando no haga nada con ellas.
  - Se cancela solo tras 120 s sin una frase útil.

## Risks / Trade-offs
- Con la voz lejos del micrófono o con mucho ruido, la puntuación baja y se pueden ignorar frases del usuario. → Registrarse a la distancia habitual y ajustar `VOICE_MATCH`.
- Cualquiera puede volver a registrar su voz. → Es una casa; si importa, pedir confirmación por Telegram.
