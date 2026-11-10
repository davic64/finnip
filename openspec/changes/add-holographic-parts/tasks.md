# Tasks

## 1. Servicio de piezas

- [x] 1.1 Crear `apps/finnip-parts`: Dockerfile (Debian 13, `openscad`, CuraEngine y definiciones de Cura 5.14 para Linux con versión fija) y servidor HTTP con clave. Comprobar dentro del contenedor las versiones y que CuraEngine cargue `creality_ender3v3se`.
- [x] 1.2 Agregar crear o versionar una pieza: rechazar `import`, `include` y `use`; renderizar con límite de 60 s, de memoria y de tamaño; devolver caja envolvente, aviso si no cabe en 220 × 220 × 250 mm y el error de OpenSCAD si falla. Verificar con pruebas: un cubo con agujero, código con `import` rechazado, un bucle que excede el tiempo, una pieza demasiado grande.
- [x] 1.3 Agregar leer una pieza con sus versiones y listar piezas. Verificar con pruebas que una versión nueva conserva las anteriores.
- [x] 1.4 Resolver la pila de Cura (máquina, material `generic_pla` o `generic_petg`, calidad `base_0.4_<material>_standard`, ajustes de la pieza) y evaluar sus fórmulas. Verificar contra los ajustes `;SETTING_3` de un G-code de Cura en la Mac, con PLA y con PETG.
- [x] 1.5 Agregar rebanar una versión con esa pila y CuraEngine, con material PLA por defecto o PETG y ajustes de la pieza validados contra las definiciones. Leer tiempo y gramos del G-code y devolver material y ajustes cambiados. Verificar con pruebas: el cubo de 1.2 en PLA y PETG (temperaturas distintas en el G-code), con `infill_sparse_density=40`, y una clave inexistente rechazada. Comparar el tiempo con el de Cura en la Mac.
- [x] 1.6 Agregar el servicio a `compose.yaml` (red interna, sin puertos, solo lectura salvo `data/parts/`, sin capacidades, límite de memoria). Requiere aprobación.

## 2. Plugin y Hermes

- [x] 2.1 Crear el plugin `finnip-parts` con `design`, `list`, `show`, `slice` (con ajustes opcionales de Cura) y `print`. `print` exige versión rebanada, impresora `Operational` sin trabajo y `confirmed: true`. Verificar con unittest y servicios falsos: imprimir sin rebanar o con la impresora ocupada se rechaza sin llamar a OctoPrint.
- [x] 2.2 Agregar a `SOUL.md`: holgura por defecto de 0.5 mm en ajustes, decir nombre, tiempo y filamento y preguntar si la cama está libre antes de imprimir, y cuándo proponer una prueba de ajuste.

## 3. Voice gateway

- [x] 3.1 Servir `data/parts` en solo lectura en `/parts/` y reenviar a la app el evento `part` cuando el plugin pide `show`. Verificar con pruebas que no se puede salir de `data/parts` con la ruta.
- [x] 3.2 Agregar la petición de foto: el plugin la pide, el gateway se la pide a la app de escritorio conectada, y responde con error claro si no hay ninguna. Verificar con pruebas.

## 4. Holograma de la pieza

- [x] 4.1 Visor STL en el overlay: aristas y superficie tenue con el color y el bloom actuales, medidas en mm, núcleo oculto mientras está abierta. Verificar a ojo con el cubo y una pieza real.
- [ ] 4.2 Mouse solo sobre el recuadro de la pieza (arrastrar gira, rueda acerca) y comandos de voz de vista resueltos en la app. Verificar que fuera del recuadro los clics siguen llegando a las demás apps.

## 5. Gestos

- [x] 5.1 Incluir `@mediapipe/tasks-vision` y el modelo de manos en la app, sin CDN. Encender la cámara al abrir una pieza y apagarla al cerrarla.
- [x] 5.2 Gestos: pellizco y arrastre gira, dos manos acercan, mano abierta 1 s restablece la vista, puño cierra. Verificar con la cámara de la Mac.
- [ ] 5.3 Agregar `NSCameraUsageDescription` a la app de escritorio y recompilarla. Verificar que macOS pide permiso una vez y que la luz de la cámara se apaga al cerrar la pieza.

## 6. Medidas

- [ ] 6.1 Agregar `look` al plugin: guarda la foto y se la da al modelo como imagen. Verificar que Hermes la recibe y describe el objeto.
- [ ] 6.2 Probar los tres caminos: un objeto conocido (medidas oficiales), medidas dictadas, y estimación con tarjeta de crédito marcada como aproximada.

## 7. Impresión

- [ ] 7.1 `print` sube el G-code a OctoPrint con `select` y `print`. Verificar con un OctoPrint falso y después con una prueba de ajuste real pequeña.

## 8. Verificación integral

- [ ] 8.1 Recorrer con el usuario, por voz:
  - Diseñar un soporte simple y verlo en el holograma.
  - Girarlo con el mouse, por voz y con gestos.
  - Cambiar una medida y ver la versión nueva.
  - Medir un objeto con la cámara y diseñar una pieza que encaje.
  - Imprimir la prueba de ajuste con confirmación.

  Anotar los resultados en el PR.

## Workflow follow-up

- Abrir un PR por fase si conviene: servicio y plugin (1–3), holograma y gestos (4–5), medidas e impresión (6–7). El usuario hace el merge.
- Archivar el cambio en OpenSpec después del último merge.
