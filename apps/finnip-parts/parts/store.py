"""Parts on disk: <root>/<slug>/part.json plus v<n>.scad, v<n>.stl, v<n>.gcode and v<n>.slice.json.

Only the latest version is kept: a new one replaces the files of the previous ones. Numbers keep growing,
so a hologram or a print never mixes up an old file with the new one."""

import datetime
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

from . import cura, scad

SLUG = re.compile(r"^[a-z0-9_]{1,40}$")
FILES = {"scad": "text/plain; charset=utf-8", "stl": "model/stl", "gcode": "text/plain; charset=utf-8"}


class NotFound(LookupError):
    pass


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _write_json(path, data):
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, suffix=".tmp") as tmp:
        json.dump(data, tmp, ensure_ascii=False, indent=1)
    os.replace(tmp.name, path)


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        for path in self.root.glob("*/part.json"):  # parts saved while every version was kept
            meta = json.loads(path.read_text())
            if len(meta["versions"]) > 1:
                meta["versions"] = meta["versions"][-1:]
                self._prune(path.parent, meta["versions"][0]["version"])
                _write_json(path, meta)

    @staticmethod
    def _prune(folder, keep):
        for file in folder.glob("v*.*"):
            if file.name.split(".")[0] != f"v{keep}":
                file.unlink()

    def _dir(self, slug):
        if not SLUG.match(slug or ""):
            raise scad.RenderError("Nombre de pieza inválido: usa minúsculas, números y guion bajo")
        return self.root / slug

    def _meta(self, slug):
        path = self._dir(slug) / "part.json"
        if not path.exists():
            raise NotFound(f"La pieza {slug} no existe")
        return json.loads(path.read_text())

    def _version(self, meta, version):
        found = [v for v in meta["versions"] if v["version"] == version]
        if not found:
            raise NotFound(f"La pieza {meta['slug']} no tiene la versión {version}")
        return found[0]

    def list(self):
        parts = []
        for path in sorted(self.root.glob("*/part.json")):
            meta = json.loads(path.read_text())
            latest = meta["versions"][-1]
            parts.append({"slug": meta["slug"], "name": meta["name"], "versions": len(meta["versions"]),
                          "size_mm": latest["size_mm"], "updated": latest["created"]})
        return parts

    def get(self, slug, version=None):
        """The part with all its versions, and the code and slice of one (the latest by default)."""
        meta = self._meta(slug)
        chosen = self._version(meta, version or meta["versions"][-1]["version"])
        folder = self._dir(slug)
        n = chosen["version"]
        sliced = folder / f"v{n}.slice.json"
        return {**meta, "current": {**chosen, "code": (folder / f"v{n}.scad").read_text(),
                                    "slice": json.loads(sliced.read_text()) if sliced.exists() else None}}

    def add_version(self, slug, code, name=None, description=None, note=None):
        """Renders the code as a new version; a failed render leaves the part as it was."""
        folder = self._dir(slug)
        folder.mkdir(exist_ok=True)
        meta_path = folder / "part.json"
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {
            "slug": slug, "name": name or slug.replace("_", " "), "description": description or "",
            "created": _now(), "versions": []}
        n = (meta["versions"][-1]["version"] + 1) if meta["versions"] else 1
        try:
            result = scad.render(code, folder / f"v{n}.scad", folder / f"v{n}.stl")
        except Exception:
            for suffix in ("scad", "stl"):
                (folder / f"v{n}.{suffix}").unlink(missing_ok=True)
            if not meta["versions"]:
                folder.rmdir() if not any(folder.iterdir()) else None
            raise
        if name:
            meta["name"] = name
        if description:
            meta["description"] = description
        record = {"version": n, "created": _now(), "note": note or "", **result}
        meta["versions"] = [record]
        _write_json(meta_path, meta)
        self._prune(folder, n)
        return record

    def delete(self, slug):
        self._meta(slug)
        shutil.rmtree(self._dir(slug))

    def slice(self, slug, version, material="PLA", settings=None):
        meta = self._meta(slug)
        self._version(meta, version)
        folder = self._dir(slug)
        result = cura.slice_stl(folder / f"v{version}.stl", folder / f"v{version}.gcode",
                                material, settings, job=f"{slug}_v{version}")
        result = {"version": version, "sliced": _now(), **result}
        _write_json(folder / f"v{version}.slice.json", result)
        return result

    def file(self, slug, version, kind):
        if kind not in FILES:
            raise NotFound("Tipo de archivo desconocido")
        path = self._dir(slug) / f"v{int(version)}.{kind}"
        if not path.exists():
            raise NotFound("Ese archivo no existe")
        return path, FILES[kind]
