"""Cura's setting stack for the Ender-3 V3 SE, resolved like Cura 5.14 does it, and CuraEngine.

CuraEngine on the command line only reads each setting's default_value; the formulas ("value",
"resolve", "limit_to_extruder") are evaluated by Cura's front end (Uranium). This module rebuilds the
same container stacks Cura makes for this printer and evaluates them the same way (UM ContainerStack,
cura GlobalStack/ExtruderStack/CuraFormulaFunctions), then passes every setting to CuraEngine.
One printer, one extruder: the multi-extruder paths of those classes collapse to extruder 0.
"""

import ast
import builtins
import configparser
import datetime
import json
import math
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

RESOURCES = Path(os.environ.get("CURA_RESOURCES", "/opt/cura/resources"))
ENGINE = Path(os.environ.get("CURA_ENGINE", "/opt/cura/CuraEngine"))
MACHINE = "creality_ender3v3se"
EXTRUDER = "creality_base_extruder_0"
VARIANT = "variants/creality/creality_ender3v3se_0.4.inst.cfg"
GLOBAL_QUALITY = "quality/creality/base/base_global_standard.inst.cfg"
# Material -> (Cura material profile, Creality quality for it with the 0.4 mm nozzle)
MATERIALS = {
    "PLA": ("generic_pla_175", "quality/creality/base/base_0.4_PLA_standard.inst.cfg"),
    "PETG": ("generic_petg_175", "quality/creality/base/base_0.4_PETG_standard.inst.cfg"),
}
# plugins/XmlMaterialProfile: material XML setting names -> Cura settings
XML_SETTINGS = {
    "print temperature": "default_material_print_temperature",
    "heated bed temperature": "default_material_bed_temperature",
    "standby temperature": "material_standby_temperature",
    "processing temperature graph": "material_flow_temp_graph",
    "print cooling": "cool_fan_speed",
    "retraction amount": "retraction_amount",
    "retraction speed": "retraction_speed",
    "adhesion tendency": "material_adhesion_tendency",
    "surface energy": "material_surface_energy",
    "build volume temperature": "build_volume_temperature",
    "anti ooze retract position": "material_anti_ooze_retracted_position",
    "anti ooze retract speed": "material_anti_ooze_retraction_speed",
}
FUNCTIONS = {"value", "resolve", "limit_to_extruder", "minimum_value", "maximum_value",
             "minimum_value_warning", "maximum_value_warning"}
# Per-part settings may change how the part prints, never the machine or its G-code scripts.
FORBIDDEN = re.compile(r"^machine_|_gcode$|_code$|^extruder_nr$|^extruders_enabled_count$")
XML_NS = {"m": "http://www.ultimaker.com/material"}


class SettingsError(ValueError):
    pass


class Formula:
    """A Uranium SettingFunction: a Python expression over other settings, evaluated from a stack."""

    def __init__(self, source):
        self.source = source
        tree = ast.parse(source, mode="eval")
        self.names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        self.code = compile(tree, source, "eval")

    def __call__(self, stack):
        variables = {}
        for name in self.names:
            if stack.knows(name):
                value = stack.value(name)
                if value is not None:
                    variables[name] = value
        try:
            return eval(self.code, {"__builtins__": builtins, "math": math, **stack.operators()}, variables)
        except Exception:
            return 0  # what Cura does: "Settings may be used in calculations and they need a value"


def _evaluate(raw, stack):
    return raw(stack) if isinstance(raw, Formula) else raw


def _find(name):
    for folder in ("definitions", "extruders"):
        path = RESOURCES / folder / f"{name}.def.json"
        if path.exists():
            return path
    raise FileNotFoundError(name)


def load_definition(name):
    """Every setting of a definition and its parents: key -> properties (functions as Formula)."""
    data = json.loads(_find(name).read_text())
    settings = load_definition(data["inherits"]) if "inherits" in data else {}
    settings = {key: dict(props) for key, props in settings.items()}

    def walk(nodes):
        for key, node in nodes.items():
            if node.get("type") != "category":
                settings[key] = {k: v for k, v in node.items() if k != "children"}
            walk(node.get("children", {}))

    walk(data.get("settings", {}))
    for key, props in data.get("overrides", {}).items():
        settings.setdefault(key, {}).update(props)
    for props in settings.values():
        for prop in FUNCTIONS & props.keys():
            if isinstance(props[prop], str) and not isinstance(props[prop], Formula):
                props[prop] = Formula(props[prop])
    return settings


def typed(definition, key, text):
    """A literal from a profile as Cura stores it, by the setting's type."""
    kind = definition.get(key, {}).get("type")
    text = str(text).strip()
    if kind == "float":
        return float(text)
    if kind == "int":
        return int(round(float(text)))
    if kind == "bool":
        return text.lower() in ("true", "1", "yes")
    if kind in ("[int]", "polygon", "polygons", "vec3"):
        return ast.literal_eval(text)
    return text


def load_profile(relative, definition):
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(RESOURCES / relative)
    values = dict(parser["values"]) if parser.has_section("values") else {}
    return {key: Formula(text[1:]) if text.startswith("=") else typed(definition, key, text)
            for key, text in values.items()}


def load_material(name, definition):
    root = ET.parse(RESOURCES / "materials" / f"{name}.xml.fdm_material").getroot()
    values = {}
    # Only the common settings: the Ender-3 V3 SE has no machine-specific materials (has_machine_materials).
    for setting in root.findall("m:settings/m:setting", XML_NS):
        key = XML_SETTINGS.get(setting.get("key"))
        if key:
            values[key] = typed(definition, key, setting.text)
    diameter = root.find("m:properties/m:diameter", XML_NS)
    if diameter is not None:
        values["material_diameter"] = float(diameter.text)
    meta = {tag: root.findtext(f"m:metadata/{path}", default="", namespaces=XML_NS)
            for tag, path in (("guid", "m:GUID"), ("type", "m:name/m:material"), ("brand", "m:name/m:brand"))}
    meta["density"] = float(root.findtext("m:properties/m:density", default="0", namespaces=XML_NS))
    return values, meta


class Stack:
    """UM ContainerStack: layers on top of a definition; [user, quality_changes, intent, quality,
    material, variant, definition_changes] as in Cura, so container indexes match."""

    def __init__(self, definition, layers):
        self.definition = definition
        self.layers = layers
        self.next = None
        self.machine = None  # set by Machine
        self.cache = {}

    def knows(self, key):
        return key in self.definition or (self.next is not None and self.next.knows(key))

    def prop(self, key, name, default=None):
        """A non-value property comes from the definition (own, else the next stack's)."""
        if key in self.definition:
            return self.definition[key].get(name, default)
        return self.next.prop(key, name, default) if self.next else None

    def raw(self, key):
        for layer in self.layers:
            if key in layer:
                return layer[key]
        if key in self.definition:
            props = self.definition[key]
            return props["value"] if "value" in props else props.get("default_value", 0)
        return self.next.raw(key) if self.next else None

    def operators(self):
        return self.machine.operators

    def value(self, key):
        if not self.machine.resolving and key in self.cache:
            return self.cache[key]
        result = self.compute(key)
        if not self.machine.resolving:
            self.cache[key] = result
        return result


class ExtruderStack(Stack):
    def compute(self, key):
        if not self.prop(key, "settable_per_extruder", True):
            return self.next.value(key)
        return _evaluate(self.raw(key), self)


class GlobalStack(Stack):
    def compute(self, key):
        resolve = self.prop(key, "resolve")
        if resolve is not None and key not in self.machine.resolving and key not in self.layers[0]:
            self.machine.resolving.add(key)
            try:
                result = _evaluate(resolve, self)
            finally:
                self.machine.resolving.discard(key)
            if result is not None:
                return result
        limit = _evaluate(self.prop(key, "limit_to_extruder", "-1"), self)
        if limit is not None and str(limit) == "0" and self.prop(key, "settable_per_extruder", True):
            return self.machine.extruder.value(key)
        return _evaluate(self.raw(key), self)


class Machine:
    """The global stack and extruder 0 for one material and set of per-part settings."""

    def __init__(self, material="PLA", settings=None):
        material = material.upper()
        if material not in MATERIALS:
            raise SettingsError(f"Material no soportado: {material}. Usa {', '.join(MATERIALS)}")
        self.material = material
        self.resolving = set()
        global_def = load_definition(MACHINE)
        extruder_def = load_definition(EXTRUDER)
        material_name, quality = MATERIALS[material]
        material_values, self.material_meta = load_material(material_name, global_def)
        user_global, user_extruder = {}, {}
        for key, value in self.check(global_def, settings or {}).items():
            per_extruder = global_def[key].get("settable_per_extruder", True)
            (user_extruder if per_extruder else user_global)[key] = value
        self.globals = GlobalStack(global_def, [
            user_global, {}, {}, load_profile(GLOBAL_QUALITY, global_def), {}, {}, {"extruders_enabled_count": 1}])
        self.extruder = ExtruderStack(extruder_def, [
            user_extruder, {}, {}, load_profile(quality, global_def), material_values,
            load_profile(VARIANT, global_def), {}])
        self.extruder.next = self.globals
        self.globals.machine = self.extruder.machine = self
        self.operators = self._operators()
        self.settings = dict(user_global, **user_extruder)
        self.validate()

    @staticmethod
    def check(definition, settings):
        values = {}
        for key, raw in settings.items():
            if key not in definition or FORBIDDEN.search(key):
                raise SettingsError(f"Ajuste no permitido: {key}")
            props = definition[key]
            try:
                value = typed(definition, key, raw if not isinstance(raw, bool) else str(raw))
            except (ValueError, SyntaxError) as error:
                raise SettingsError(f"Valor inválido para {key}: {raw}") from error
            if props.get("type") == "enum" and value not in props.get("options", {}):
                raise SettingsError(f"{key} acepta: {', '.join(props.get('options', {}))}")
            values[key] = value
        return values

    def validate(self):
        """Per-part values against Cura's limits, like its validator: outside minimum_value/maximum_value
        is an error (Cura will not slice); outside the *_warning limits is a warning to tell the user."""
        self.warnings = []
        for key, value in self.settings.items():
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            stack = self.extruder if self.globals.prop(key, "settable_per_extruder", True) else self.globals
            limits = {name: _evaluate(stack.prop(key, name), stack) for name in (
                "minimum_value", "maximum_value", "minimum_value_warning", "maximum_value_warning")}
            low, high = limits["minimum_value"], limits["maximum_value"]
            if low is not None and value < low or high is not None and value > high:
                raise SettingsError(f"{key}={value} fuera de rango ({low} a {high})")
            low, high = limits["minimum_value_warning"], limits["maximum_value_warning"]
            if low is not None and value < low or high is not None and value > high:
                self.warnings.append(f"{key}={value} fuera de lo recomendado por Cura ({low} a {high})")

    def _operators(self):
        ext, glob = self.extruder, self.globals

        def in_extruder(key):
            value = _evaluate(ext.raw(key), ext)
            return value.lower() if isinstance(value, str) else value

        def all_extruders(key):
            raw = ext.raw(key)
            return [glob.value(key)] if raw is None else [_evaluate(raw, ext)]

        def from_container(stack, key, index):
            container = stack.layers[index] if index < len(stack.layers) else None
            if container is None:
                props = stack.definition.get(key, {})
                raw = props.get("value", props.get("default_value"))
            else:
                raw = container.get(key)
            return _evaluate(raw, stack)

        return {
            "extruderValue": lambda position, key: in_extruder(key),
            "extruderValues": all_extruders,
            "anyExtruderNrWithOrDefault": lambda key: "0" if ext.raw(key) else None,
            "anyExtruderWithMaterial": lambda key: "0",
            "resolveOrValue": lambda key: glob.value(key),
            "defaultExtruderPosition": lambda: "0",
            "valueFromContainer": lambda key, index: from_container(glob, key, index),
            "extruderValueFromContainer": lambda position, key, index: from_container(ext, key, index),
        }

    def global_settings(self, job="finnip"):
        """What Cura's StartSliceJob sends as global settings, tokens for the start G-code included."""
        settings = {key: self.globals.value(key) for key in self.globals.definition}
        now = datetime.datetime.now()
        settings.update({
            "quality_name": "Standard Quality", "print_bed_temperature": settings["material_bed_temperature"],
            "time": now.strftime("%H:%M:%S"), "date": now.strftime("%d-%m-%Y"), "day": now.strftime("%a"),
            "jobname": job,
        })
        start = re.sub(r";.+?(\n|$)", "\n", settings["machine_start_gcode"])
        for flag, names in (("material_bed_temp_prepend", "material_bed_temperature|material_bed_temperature_layer_0"),
                            ("material_print_temp_prepend", "material_print_temperature|material_print_temperature_layer_0|default_material_print_temperature|material_initial_print_temperature|material_final_print_temperature|material_standby_temperature|print_temperature")):
            if settings[flag]:
                settings[flag] = re.search(r"\{(%s)(,\s?\w+)?\}" % names, start) is None
        settings["nozzle_offsetting_for_disallowed_areas"] = True
        return settings

    def extruder_settings(self):
        """What StartSliceJob sends for extruder 0: every setting settable per extruder."""
        own = self.extruder.definition
        keys = set(self.globals.definition) | set(own)
        settings = {}
        for key in keys:
            in_global = self.globals.definition[key].get("settable_per_extruder", True) if key in self.globals.definition else None
            in_own = own[key].get("settable_per_extruder", True) if key in own else None
            if (in_global is not None or in_own is not None) and not in_global and not in_own:
                continue
            settings[key] = self.extruder.value(key)
        meta = self.material_meta
        settings.update({
            "material_guid": meta["guid"], "material_id": MATERIALS[self.material][0], "material_type": meta["type"],
            "material_name": f"Generic {self.material}", "material_brand": meta["brand"],
            "material_density": meta["density"], "print_temperature": settings["material_print_temperature"],
            "travel_speed": settings["speed_travel"],
        })
        return settings


def _arg(key, value):
    return ["-s", f"{key}={value}"]


def slice_stl(stl, gcode, material="PLA", settings=None, job="finnip", timeout=300):
    """Slices an STL; returns {material, settings, seconds, grams, filament_mm}."""
    machine = Machine(material, settings)
    command = [str(ENGINE), "slice", "-m2", "-j", str(_find(MACHINE)),
               "-d", f"{RESOURCES / 'definitions'}:{RESOURCES / 'extruders'}"]
    for key, value in machine.global_settings(job).items():
        command += _arg(key, value)
    command.append("-e0")
    for key, value in machine.extruder_settings().items():
        command += _arg(key, value)
    command += ["-l", str(stl), "-o", str(gcode)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0 or not Path(gcode).exists():
        tail = [line for line in result.stderr.splitlines() if "[error]" in line][-3:]
        raise RuntimeError("CuraEngine falló: " + (" | ".join(tail) or f"código {result.returncode}"))
    stats = gcode_stats(Path(gcode).read_text(errors="replace"), machine)
    return {"material": machine.material, "settings": machine.settings, "warnings": machine.warnings, **stats}


def gcode_stats(text, machine):
    seconds = re.search(r"^;TIME:(\d+(?:\.\d+)?)", text, re.M)
    length = re.search(r"^;Filament used:\s*([\d.]+)m", text, re.M)
    filament_mm = float(length.group(1)) * 1000 if length else 0.0
    radius = machine.extruder.value("material_diameter") / 2
    grams = filament_mm * math.pi * radius ** 2 * machine.material_meta["density"] / 1000
    return {"seconds": int(float(seconds.group(1))) if seconds else None,
            "filament_mm": round(filament_mm), "grams": round(grams, 1)}
