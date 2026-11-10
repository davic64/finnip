# Proposal

## Why

El usuario imprime piezas en su Ender-3 V3 SE, pero para diseñarlas necesita un programa CAD, exportar el STL, rebanarlo y mandarlo a OctoPrint a mano. Finnip ya controla la impresora y tiene un holograma en el escritorio. Puede cerrar el ciclo completo por voz: describir la pieza, verla flotando sobre el escritorio, girarla con la mano, ajustar medidas y decir "imprímela".

## What Changes

- **Diseño por voz:**
  - Finnip escribe la pieza como código OpenSCAD a partir de lo que dice el usuario, y un servicio nuevo en el servidor la convierte en STL.
  - Cada cambio ("hazla 5 mm más alta", "agrégale un agujero de 3 mm") crea una versión nueva. Las anteriores se conservan.
  - El código corre aislado: sin red, con límite de tiempo y de memoria.
- **Holograma de la pieza:**
  - El overlay de escritorio muestra la pieza en lugar del núcleo, con el estilo del holograma y sus medidas en milímetros.
  - Se gira y se acerca con el mouse, con gestos de la mano o por voz ("vista de arriba", "gírala").
- **Gestos con la cámara:**
  - MediaPipe Hand Landmarker corre en la Mac, dentro del overlay. El video nunca sale de la Mac.
  - La cámara solo se enciende mientras hay una pieza abierta.
- **Medidas de objetos reales:**
  - Finnip puede tomar una foto con la cámara de la Mac, a petición del usuario, para identificar el objeto ("es una Raspberry Pi 4") y buscar sus medidas oficiales.
  - Si no hay medidas oficiales, el usuario las dicta (vernier o regla). Una estimación con una tarjeta de crédito como referencia sirve solo como aproximación y se marca así.
  - Las piezas que deben encajar llevan holgura (0.5 mm por defecto), y Finnip ofrece imprimir primero una prueba de ajuste corta.
- **Imprimir:**
  - "Imprímela" rebana la pieza con CuraEngine, el motor de Ultimaker Cura (la misma versión 5.14 que usa el usuario), con el perfil del Ender-3 V3 SE y los valores por defecto de Cura para el material de la pieza: PLA (por defecto) o PETG. Si el usuario pide ajustes para una pieza ("relleno al 40 %", "con soportes"), se guardan con esa pieza. Responde con tiempo, filamento y los ajustes usados.
  - Finnip imprime solo después de que el usuario confirma que la cama está libre, y solo si la impresora está lista. Los avisos de fin de impresión siguen siendo los del plugin de la impresora.
- **Fuera de alcance:** descargar STL de internet, editar mallas a mano, varios materiales o colores, y detectar con cámara si la cama está libre.

## Capabilities

### New Capabilities

- `part-design`: diseñar piezas por voz como código OpenSCAD, renderizarlas a STL de forma aislada y conservar sus versiones.
- `part-hologram`: mostrar una pieza en el overlay de escritorio, girarla y acercarla con mouse, voz o gestos de la mano.
- `part-measurement`: obtener medidas de objetos reales (especificaciones oficiales, dictadas o estimadas con la cámara), con holgura y prueba de ajuste.
- `part-printing`: rebanar una pieza con CuraEngine para el Ender-3 V3 SE e imprimirla con OctoPrint después de la confirmación del usuario.

### Modified Capabilities

- `desktop-overlay`: el overlay puede mostrar una pieza en lugar del núcleo, encender la cámara mientras está abierta y recibir el mouse solo sobre la pieza.

## Impact

- **Servicio nuevo `apps/finnip-parts`:** contenedor Debian 13 con OpenSCAD 2021.01 y CuraEngine 5.14, solo en la red de Compose, sin puertos publicados. Guarda las piezas en `data/parts/` (fuera del repo).
- **Plugin nuevo `finnip-parts` para Hermes:** acciones para diseñar, listar, mostrar, medir, rebanar e imprimir. Reglas nuevas en `SOUL.md`.
- **Voice gateway:** sirve los STL al overlay, avisa a la app qué pieza mostrar y pide a la Mac una foto cuando el usuario lo solicita.
- **App (`apps/finnip-app`) y app de escritorio (`apps/finnip-desktop`):** visor STL con estilo holograma, gestos con MediaPipe (incluido localmente, sin CDN) y permiso de cámara de macOS.
- **Impresora:** se reutiliza OctoPrint y el plugin `finnip-printer`. Se sube el G-code por su API.
- **Compose:** un servicio nuevo y un volumen. Requiere aprobación antes de desplegar.
- **Privacidad:** la foto para medir solo se toma a petición del usuario y se manda al modelo de Hermes. El video de los gestos no sale de la Mac.
