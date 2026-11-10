"""OpenSCAD code written by the model -> STL, isolated: no file access, time, memory and size limits."""

import os
import re
import resource
import signal
import struct
import subprocess
from pathlib import Path

OPENSCAD = os.environ.get("OPENSCAD", "openscad")
TIMEOUT_S = 60
MEMORY_BYTES = 1024 * 1024 * 1024  # 1 GiB address space for one render
MAX_STL_BYTES = 64 * 1024 * 1024
BED_MM = (220, 220, 250)  # Ender-3 V3 SE build volume
# The only ways OpenSCAD code reaches files: import/include/use, surface() and the old dxf_* modules.
FILE_ACCESS = re.compile(r"\b(import|include|use|surface|dxf_\w+)\b")


class RenderError(ValueError):
    pass


def strip_comments_and_strings(code):
    code = re.sub(r"/\*.*?\*/", " ", code, flags=re.S)
    code = re.sub(r"//[^\n]*", " ", code)
    return re.sub(r'"(?:\\.|[^"\\])*"', '""', code)


def check(code):
    """Rejects code that would read files; the reason is returned to the model so it can fix it."""
    if len(code) > 100_000:
        raise RenderError("El código es demasiado largo")
    found = FILE_ACCESS.search(strip_comments_and_strings(code))
    if found:
        raise RenderError(f"No se permite '{found.group(1)}': la pieza debe hacerse solo con código")


def _limits():
    os.setsid()  # own process group, so a timeout kills it whole
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_BYTES, MEMORY_BYTES))
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_STL_BYTES, MAX_STL_BYTES))


def read_stl(path):
    """Triangles of an ASCII or binary STL as [(v1, v2, v3)]."""
    data = Path(path).read_bytes()
    if data[:5] == b"solid" and b"facet" in data[:400]:
        nums = re.findall(rb"vertex\s+(\S+)\s+(\S+)\s+(\S+)", data)
        vertices = [tuple(float(n) for n in v) for v in nums]
        return [tuple(vertices[i:i + 3]) for i in range(0, len(vertices) - 2, 3)]
    count = struct.unpack_from("<I", data, 80)[0]
    triangles = []
    for i in range(count):
        values = struct.unpack_from("<12f", data, 84 + i * 50)
        triangles.append((values[3:6], values[6:9], values[9:12]))
    return triangles


def write_stl(path, triangles):
    with open(path, "wb") as out:
        out.write(b"finnip".ljust(80, b" ") + struct.pack("<I", len(triangles)))
        for a, b, c in triangles:
            out.write(struct.pack("<12fH", 0, 0, 0, *a, *b, *c, 0))


def bounds(triangles):
    points = [p for triangle in triangles for p in triangle]
    return [min(p[i] for p in points) for i in range(3)], [max(p[i] for p in points) for i in range(3)]


def render(code, scad_path, stl_path):
    """Writes code to scad_path and the part to stl_path, centered on X/Y and resting on Z=0 (as Cura
    places it on the bed). Returns {size_mm, warnings}."""
    check(code)
    scad_path, stl_path = Path(scad_path), Path(stl_path)
    scad_path.write_text(code)
    raw = stl_path.with_suffix(".raw.stl")
    try:
        process = subprocess.Popen([OPENSCAD, "--export-format", "asciistl", "-o", str(raw), str(scad_path)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   preexec_fn=_limits, cwd=scad_path.parent)
        try:
            _, log = process.communicate(timeout=TIMEOUT_S)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            raise RenderError(f"El render tardó más de {TIMEOUT_S} s; simplifica la pieza")
        errors = [line for line in log.splitlines() if line.startswith(("ERROR", "Parser error"))]
        if process.returncode != 0 or errors or not raw.exists():
            if "Current top level object is empty" in log:
                raise RenderError("La pieza está vacía")
            raise RenderError("OpenSCAD: " + " | ".join(errors[-3:] or log.strip().splitlines()[-3:]))
        triangles = read_stl(raw)
        if not triangles:
            raise RenderError("La pieza está vacía")
        low, high = bounds(triangles)
        shift = [-(low[0] + high[0]) / 2, -(low[1] + high[1]) / 2, -low[2]]
        write_stl(stl_path, [tuple(tuple(p[i] + shift[i] for i in range(3)) for p in t) for t in triangles])
    finally:
        raw.unlink(missing_ok=True)
    size = [round(high[i] - low[i], 2) for i in range(3)]
    warnings = []
    if any(s > limit for s, limit in zip(size, BED_MM)):
        warnings.append("No cabe en la cama de la impresora (220 × 220 × 250 mm)")
    if "2-manifold" in log:
        warnings.append("OpenSCAD avisa que la pieza puede no ser un sólido cerrado")
    return {"size_mm": size, "warnings": warnings}
