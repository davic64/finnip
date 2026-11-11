# Proposal

## Why
El usuario quiere a Finnip frente a él como si fuera un Echo, con pantalla y holograma, sin depender de que la Mac esté prendida y escuchando. Tiene un Xiaomi Redmi Note 9 que ya no usa: tiene micrófono, bocina y pantalla, y mucha más potencia que un ESP32. La app web de Finnip ya funciona a pantalla completa en un navegador, así que basta con envolverla en una app Android. Al mismo tiempo, la Mac debe poder dejar de escuchar sin dejar de mostrar cosas: lo que pide desde el celular y se ve mejor en grande (estado del servidor, agenda, piezas) aparece en la Mac.

## What Changes
- **App Android (`apps/finnip-phone`):**
  - APK propia: una actividad con un WebView que carga la app web con `?phone=1` a pantalla completa, sin barras.
  - Siempre escucha "Finnip": el micrófono se abre al arrancar y no hay forma de apagarlo desde la app, como un Echo.
  - La pantalla nunca se apaga. Sin conversación, baja el brillo real al mínimo; al oír "Finnip" o al hablar, lo regresa.
  - Puede ser la pantalla de inicio del celular (modo kiosco): arranca sola al prender y el botón de inicio vuelve a Finnip.
- **App web:** modo `?phone=1`: abre el micrófono sin esperar un toque y le dice a la app Android cuándo atenuar.
- **Voice gateway:** si hay una Mac conectada y la pregunta llega de otro dispositivo, el estado del servidor y la agenda se muestran en la Mac. El celular solo responde con voz. Las piezas y la cámara ya iban solo a la Mac.
- **App de escritorio:**
  - "Escuchar «Finnip»" en el menú (antes "Silenciar micrófono") se recuerda al reiniciar la app.
  - Con la escucha desactivada, el atajo global abre el micrófono para una sola frase y lo vuelve a cerrar al terminar la respuesta.
  - Los paneles que llegan del celular se ocultan solos.
- **Fuera de alcance:**
  - Wake word en el propio celular (sin mandar frases al servidor).
  - Limitar la carga de la batería: necesita un enchufe inteligente en Home Assistant y queda para después.
  - Publicar el APK en una tienda.

## Capabilities

### New Capabilities
- `phone-satellite`: app Android que deja un celular viejo como bocina con pantalla de Finnip, siempre escuchando y con brillo atenuado en reposo.

### Modified Capabilities
- `desktop-overlay`: la escucha de la Mac se activa o desactiva desde el menú y se recuerda; el atajo sirve para una frase con la escucha desactivada; los paneles pedidos desde el celular se muestran en la Mac.
