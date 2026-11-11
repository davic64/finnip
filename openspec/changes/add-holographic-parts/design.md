# Design

## Context

- La impresora es una Creality Ender-3 V3 SE con OctoPrint (`print.finnip`). El plugin `finnip-printer` ya calienta, carga filamento, vigila el estado cada 3 s y avisa por voz y Telegram al terminar.
- El overlay de escritorio (`apps/finnip-desktop`, Tauri v2) carga la app web (`apps/finnip-app`) desde el servidor. Dibuja el holograma con Three.js y bloom, en un recuadro transparente. Ya usa el micrófono de la Mac.
- El voice gateway habla con la app por WebSocket y con Hermes por `/v1/responses`. Caddy protege todo con `tailscale_auth`.
- El servidor es un HP EliteBook con 4 núcleos y 8 GB de RAM. El modelo principal de Hermes (Claude Sonnet 5.5) acepta imágenes.
- El usuario rebana con Ultimaker Cura 5.14 en su Mac, con la máquina `creality_ender3v3se`.
- Debian 13 trae `openscad` 2021.01, pero Cura y CuraEngine solo en 5.0 (2022), sin el perfil del Ender-3 V3 SE.

## Goals / Non-Goals

**Goals:**
- Del "quiero una pieza que…" a la pieza impresa, por voz, viendo el resultado antes de imprimir.
- Que ningún código escrito por el modelo pueda tocar el servidor ni la red.
- Que nada se imprima sin una confirmación explícita del usuario.

**Non-Goals:**
- Un CAD completo: no hay edición de vértices ni de mallas.
- Importar STL de internet, imprimir con varios materiales, o detectar la cama libre con cámara.
- Medidas de precisión con la cámara. La cámara identifica; las medidas finas las dicta el usuario o vienen de la ficha técnica.

## Decisions

### OpenSCAD como formato de la pieza
El modelo escribe OpenSCAD, no Python (CadQuery o build123d).
- OpenSCAD es un lenguaje declarativo sin acceso a archivos, procesos ni red, salvo `import`/`include`/`use`. El servicio los rechaza antes de renderizar.
- Los modelos de lenguaje lo conocen bien, y una pieza paramétrica cabe en pocas líneas que Finnip puede editar.
- *Alternativa: CadQuery.* Es más potente para filetes y chaflanes, pero es Python arbitrario y exige un aislamiento mucho más fuerte. Se descarta.
- La versión 2021.01 usa CGAL, que es lento con muchas operaciones booleanas. Para piezas funcionales simples alcanza. Si se queda corto, se cambia a una versión con Manifold (comentario `ponytail`).

### Servicio `finnip-parts`
Un servicio HTTP pequeño en Python, en su propio contenedor (Debian 13 + `openscad` + CuraEngine 5.14).
- Rutas: crear o versionar una pieza (`scad` → STL), leer una pieza y sus versiones, rebanar una versión (`material` → G-code con tiempo y filamento estimados).
- Cada render corre como proceso con límite de tiempo (60 s), de memoria y de tamaño de salida. El contenedor es de solo lectura salvo `data/parts/`, sin capacidades y sin puertos publicados. Solo lo ven Hermes y el voice gateway por la red de Compose, y pide una clave como Home Bridge.
- Al renderizar devuelve la caja envolvente en mm y avisa si la pieza no cabe en la cama (220 × 220 × 250 mm) o no es un sólido válido.
- Las piezas viven en `data/parts/<slug>/v<n>.scad|.stl|.gcode`, con un `part.json` con nombre, descripción y medidas.

### Plugin `finnip-parts`
Herramienta para el modelo con acciones `design` (nueva pieza o versión), `list`, `show`, `look` (foto de la cámara), `slice` y `print`.
- `show` le pide al gateway que el overlay abra la pieza.
- `print` exige una versión ya rebanada, la impresora en estado `Operational` y sin trabajo, y `confirmed: true`. La descripción de la herramienta y `SOUL.md` piden decir antes nombre, tiempo, filamento y preguntar si la cama está libre.
- El plugin no aplica holguras por su cuenta: las incluye el modelo en el código, con el valor por defecto que fija `SOUL.md`.

### Mostrar la pieza
- El gateway sirve `/parts/<slug>/v<n>.stl`, detrás de la misma autenticación de Caddy, pidiéndolo al servicio de piezas con su clave. Así el navegador nunca tiene la clave, el gateway no monta `data/parts` y un nombre inválido no puede salir de la carpeta.
- Las rutas `/internal/part` y `/internal/photo` son para Hermes dentro de la red de Compose: no llevan el header de Tailscale y piden `PARTS_API_KEY`.
- La app de escritorio se identifica con `client: "desktop"` en su `hello`. Solo ella recibe las piezas y las peticiones de foto; si hay varias, la conectada más reciente.
- Un evento `part` por WebSocket (`{slug, version, url, size_mm}`) hace que la app cargue el STL con `STLLoader`.
- Estilo: aristas con `EdgesGeometry` y una superficie tenue con brillo en los bordes (fresnel), en el color de los monitores y con el bloom actual. Las medidas en mm aparecen junto a la pieza.
- El núcleo se oculta mientras la pieza está abierta y vuelve al cerrarla ("cierra la pieza", gesto de puño o `Esc`).

### Interacción: mouse, voz y gestos
- **Mouse:** el overlay normalmente deja pasar los clics. Con una pieza abierta, Tauri deja de ignorar el cursor solo dentro del recuadro de la pieza: arrastrar gira, la rueda acerca.
- **Voz:** "vista de arriba", "de frente", "gírala", "más cerca" se resuelven en la app, sin llamar al modelo.
- **Gestos:** MediaPipe Hand Landmarker (`@mediapipe/tasks-vision`, WASM con GPU), con el modelo y el runtime servidos por la app, sin CDN.
  - Pellizco y arrastre: girar. Pellizco con dos manos: acercar o alejar. Mano abierta 1 s: vista inicial. Puño: cerrar la pieza.
  - La cámara se enciende al abrir una pieza y se apaga al cerrarla. La app desktop declara `NSCameraUsageDescription`, y macOS pide permiso una vez.
- *Alternativa: gestos en el servidor.* Habría que mandar el video por la red. Se descarta.

### Fotos para medir
- `look` pide al gateway una foto. El gateway se la pide a la app de escritorio conectada, que toma un cuadro de la cámara, lo reduce a 1024 px y lo devuelve en JPEG. El plugin lo guarda y se lo da al modelo como imagen.
- Solo ocurre cuando el usuario lo pide ("mira esto", "mídelo"). La app muestra que tomó la foto.
- Con la imagen, el modelo identifica el objeto y busca sus medidas oficiales, o estima con una tarjeta de crédito (85.60 × 53.98 mm) en el mismo plano. Las estimaciones se marcan como aproximadas y Finnip pide confirmar las medidas que importan para el ajuste.
- Para piezas que deben encajar, Finnip propone una prueba de ajuste: solo la parte crítica, en una capa delgada o un anillo, de unos minutos de impresión.

### Rebanar con CuraEngine
- Se usa CuraEngine, no PrusaSlicer, para que la pieza salga igual que si el usuario la rebanara en su Cura.
- El binario y las definiciones (`fdmprinter`, `creality_base`, `creality_ender3v3se` y su extrusor) se toman de la versión oficial de Cura 5.14 para Linux al construir la imagen, con la versión fija. Debian 5.0 no tiene la máquina.
- Material: PLA (por defecto) o PETG, el que diga el usuario para la pieza. Se guarda con la versión.
- Base: la misma pila que arma Cura para `creality_ender3v3se`: definiciones de la máquina, perfil del material (`generic_pla` o `generic_petg`: temperaturas, cama, ventilador, retracción) y calidad de Creality para ese material con boquilla de 0.4 y calidad estándar (`base_0.4_PLA_standard` o `base_0.4_PETG_standard`). No se copian los ajustes sin guardar del Cura de la Mac.
- CuraEngine desde línea de comandos solo lee los `default_value` de las definiciones; las fórmulas (`value`) las evalúa la interfaz de Cura. El servicio resuelve la pila y evalúa esas fórmulas (expresiones Python sobre otros ajustes, con `extruderValue`, `resolveOrValue` y `math`) antes de llamar a CuraEngine.
- Verificación contra Cura: el G-code de Cura termina con sus ajustes serializados (`;SETTING_3`). Se rebana la misma pieza en la Mac y en el servicio, con PLA y con PETG, y se comparan los ajustes y el tiempo.
- Ajustes por pieza: cuando el usuario los pide ("relleno al 40 %", "con soportes", "capa de 0.12"), Finnip los guarda en la versión de la pieza y se pasan a `CuraEngine slice` como `-s clave=valor`. El servicio solo acepta claves que existen en las definiciones de Cura, con valores del tipo y rango que estas declaran.
- El resultado de rebanar dice los ajustes que cambiaron respecto a la base, para que el usuario los vea antes de imprimir.
- El servicio lee el tiempo y los gramos de los comentarios `;TIME:` y `;Filament used:` del G-code.
- *Alternativa: copiar los ajustes del Cura de la Mac.* Son cambios sin guardar de impresiones anteriores (por ejemplo, 0 capas inferiores) y no sirven como base. Se descarta.
- *Alternativa: PrusaSlicer.* Está en Debian 13 con el perfil, pero imprimiría con otros parámetros que los de Cura. Se descarta.

### Imprimir
- La impresión sube el G-code a OctoPrint (`POST /api/files/local` con `select` y `print`). Desde ahí el plugin `finnip-printer` ya vigila y avisa.

## Risks / Trade-offs

- [El modelo escribe OpenSCAD que no compila o que no es la pieza pedida] → El servicio devuelve el error de OpenSCAD al modelo, que corrige. El usuario ve la pieza en el holograma antes de imprimir.
- [OpenSCAD 2021.01 tarda con piezas complejas] → Límite de 60 s y mensaje claro. Las piezas funcionales simples renderizan en segundos.
- [Imprimir sin que la cama esté libre] → Confirmación explícita en cada impresión. La plataforma no se puede verificar con cámara en esta versión.
- [La estimación con cámara se usa como medida exacta] → Se marca como aproximada y la prueba de ajuste es parte del flujo para piezas que encajan.
- [Consumo de GPU de los gestos en la Mac] → La cámara y MediaPipe solo corren con una pieza abierta.
- [La foto de la cámara llega al proveedor del modelo] → Solo a petición explícita del usuario, una imagen por vez, reducida. Se documenta en `SOUL.md` y en el README.
- [El servidor tiene 4 núcleos y 8 GB] → Un render y un rebanado a la vez, con límite de memoria en el contenedor.

## Migration Plan

1. Desplegar `finnip-parts` (servicio y volumen nuevos en Compose, con aprobación).
2. Desplegar el plugin y las reglas de `SOUL.md`. Reiniciar Hermes y la sesión de voz.
3. Publicar la app con el visor y los gestos. Recompilar la app de escritorio con el permiso de cámara.
4. **Vuelta atrás:** quitar el servicio y el plugin. El resto de Finnip no depende de ellos, y las piezas quedan en `data/parts/`.
