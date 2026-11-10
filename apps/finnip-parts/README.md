# finnip-parts

Servicio de piezas 3D de Finnip: convierte código OpenSCAD en STL, guarda versiones y rebana con CuraEngine para la Creality Ender-3 V3 SE. Solo lo usan Hermes (plugin `finnip-parts`) y el voice gateway, dentro de la red de Compose.

## Rutas

Todas piden `Authorization: Bearer $PARTS_API_KEY`, menos `/health`.

| Método | Ruta | Cuerpo |
|---|---|---|
| `GET` | `/health` | — |
| `GET` | `/parts` | — |
| `GET` | `/parts/<slug>?version=n` | — (sin `version`, la última) |
| `POST` | `/parts/<slug>/versions` | `{ "code": "…", "name": "Soporte", "description": "…", "note": "más alto" }` |
| `POST` | `/parts/<slug>/versions/<n>/slice` | `{ "material": "PLA" \| "PETG", "settings": { "infill_sparse_density": 40 } }` |
| `GET` | `/parts/<slug>/v<n>.stl` · `.gcode` · `.scad` | — |

Errores: `400` código o ajuste inválido (el mensaje sirve para que el modelo corrija), `404` pieza o versión inexistente, `401` sin clave.

## Render aislado (`parts/scad.py`)

- Se rechaza el código con `import`, `include`, `use`, `surface` o `dxf_*`, las únicas formas en que OpenSCAD lee archivos.
- Cada render tiene 60 s, 1 GiB de memoria y 64 MiB de salida. El contenedor corre sin privilegios y solo escribe en `/data/parts`.
- El STL se guarda centrado en X/Y y apoyado en Z=0, como Cura coloca la pieza en la cama. Se avisa si no cabe en 220 × 220 × 250 mm.

## Rebanado (`parts/cura.py`)

CuraEngine en línea de comandos solo lee los `default_value` de las definiciones. Las fórmulas de Cura (`value`, `resolve`, `limit_to_extruder`) las evalúa su interfaz. Este módulo arma la misma pila que Cura 5.14 para esta impresora y la evalúa igual:

| Pila | Contenedores (de arriba hacia abajo) |
|---|---|
| Global | ajustes de la pieza, `base_global_standard`, `extruders_enabled_count = 1`, `creality_ender3v3se` |
| Extrusor 0 | ajustes de la pieza, `base_0.4_<material>_standard`, `generic_<material>_175`, `creality_ender3v3se_0.4`, `creality_base_extruder_0` |

- Material: PLA (por defecto) o PETG.
- Ajustes por pieza: solo claves de Cura que no empiezan con `machine_` ni son G-code. Fuera de `minimum_value`/`maximum_value` se rechazan; fuera de los límites `*_warning` se devuelve un aviso.
- El resultado trae tiempo, filamento en mm y gramos (con la densidad del material), material, ajustes y avisos.

Si se actualiza Cura, se cambian `CURA_VERSION` y `CURA_SHA256` en el `Dockerfile`, y se repite la comparación con un G-code de Cura (sus ajustes van al final, en `;SETTING_3`).

## Plugin de Hermes (`plugin/`)

Herramienta `finnip_parts` con `design`, `list`, `get`, `show`, `slice` y `print`.

- `print` exige la versión ya rebanada, `confirmed: true` y la impresora conectada y libre; sube el G-code a OctoPrint con `select` y `print`. El fin de la impresión lo anuncia el plugin `finnip-printer`.
- `show` pide al voice gateway (`POST /internal/part`) que el overlay abra la pieza.
- Despliegue: copiar `plugin/__init__.py` y `plugin.yaml` a `data/hermes/plugins/finnip-parts`, habilitar `finnip-parts` y el toolset `finnip_parts` en `data/hermes/config.yaml`, y dar a Hermes `config/parts.env` (`PARTS_API_KEY`). Las reglas de confirmación y holgura están en `SOUL.md`.

## Pruebas

```sh
docker build -t finnip-parts:dev .
docker run --rm --network none finnip-parts:dev python3 -m unittest discover -s tests -v
```

Las pruebas de render y rebanado necesitan OpenSCAD y CuraEngine, por eso corren dentro de la imagen. Las del plugin no: `cd plugin && python3 -m unittest discover -s tests`.
