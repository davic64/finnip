# Tasks

## 1. Voice gateway
- [x] 1.1 `Session.show_panel`: `stats` y `reminders` van a las apps de escritorio si la sesión no es de escritorio y hay alguna conectada, y si no, a la misma sesión. Verificar con pruebas los tres casos.

## 2. App web
- [x] 2.1 Modo `?phone=1`: abrir el micrófono en reposo al cargar, sin esperar un toque.
- [x] 2.2 Llamar a `FinnipPhone.dim` con el estado: brillo normal al escuchar, pensar o hablar; atenuado tras 10 s en reposo.
- [x] 2.3 Escritorio: `?muted=1` al cargar no abre el micrófono; `mute()` actualiza la URL.
- [x] 2.4 Escritorio: con la escucha desactivada, el atajo abre el micrófono para una frase y lo cierra al volver al reposo.
- [x] 2.5 Escritorio: un panel que llega sin conversación propia se oculta solo.

## 3. App de escritorio
- [x] 3.1 `Settings.muted` guardado; la URL del overlay lleva `&muted=1`; el atajo ya no quita el silencio.
- [x] 3.2 Menú "Escuchar «Finnip»" con palomita (marcado = escuchando). Recompilar e instalar en `/Applications`.

## 4. App Android
- [x] 4.1 Proyecto Gradle `apps/finnip-phone` (Java, una actividad, `minSdk` 29), con la URL en tiempo de compilación.
- [x] 4.2 WebView a pantalla completa:
  - pantalla siempre encendida;
  - audio sin gesto;
  - `RECORD_AUDIO` concedido solo al origen de Finnip;
  - reintento si no hay conexión.
- [x] 4.3 `FinnipPhone.dim` cambia el brillo de la ventana. Categoría `HOME` para modo kiosco; el botón atrás no sale de la app.
- [ ] 4.4 Compilar el APK, instalarlo con `adb` en el Redmi Note 9 y probar: "Finnip" despierta, el brillo baja en reposo, y el estado del servidor aparece en la Mac.
