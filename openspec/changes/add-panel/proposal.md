# Proposal

## Why
Hoy, para crear un modo o una rutina ("cuando diga X, responde Y y haz Z"), el usuario tiene que pedírselo a Finnip por voz o a un desarrollador. Un modo con varias luces y colores se dicta mal, y una rutina estaba fija en el código del plugin.

## What Changes
- **Panel (`/panel.html`):**
  - Lo sirve el voice gateway, con la misma protección de Tailscale que la app.
  - Se abre desde Ajustes en el celular y desde "Modos y rutinas…" en el menú de la Mac.
- **Modos:**
  - Lista, crear, editar y borrar.
  - Cada paso es un dispositivo y una acción (encender, brillo, color, temperatura de blanco, volumen…), con controles deslizantes y selector de color.
  - Se guardan como los mismos scripts `modo_*` de Home Assistant, a través de Home Bridge.
- **Rutinas:**
  - Cada una tiene una frase, una respuesta exacta y, opcionalmente, acciones (encender o apagar luces, brillo, color, temperatura, volumen; el mismo editor de pasos que los modos), música en Alexa y un modo.
  - Se guardan en `data/routines/routines.json`, y el plugin `finnip-lights` las lee en cada frase, así que un cambio aplica sin reiniciar.
  - La rutina "despierta, ya llegó papá" pasa del código a ese archivo.
- **Fuera de alcance:** controlar las luces en vivo (eso se hace en Home Assistant), y rutinas con condiciones u horarios.

## Capabilities

### New Capabilities
- `panel`: editar modos y rutinas desde una página web, sin pedírselo a Finnip.
