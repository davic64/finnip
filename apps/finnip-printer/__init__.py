"""Finnip and the 3D printer (Ender-3 V3 SE through OctoPrint).

Orders run at once (heat, cool, purge, power). What has to wait for a temperature (the filament is
ready to go in or out, power off once the nozzle is cool) or for the print (it finished) is kept as
an intent in PRINTER_STATE and carried out by step(), which the voice gateway calls every few
seconds; step() returns the messages Finnip has to say on its own (voice and Telegram)."""
import json
import os
import tempfile
import time
import urllib.error
import urllib.request

OCTOPRINT_URL = os.environ.get("OCTOPRINT_URL", "http://octoprint").rstrip("/")
BRIDGE_URL = os.environ.get("FINNIP_BRIDGE_URL", "http://home-bridge:3000").rstrip("/")
STATE_PATH = os.environ.get("PRINTER_STATE", "/opt/finnip-printer/state.json")
POWER_SWITCH = os.environ.get("PRINTER_SWITCH", "switch.impresora")

MATERIALS = {"pla": (200, 60), "petg": (230, 70)}  # nozzle, bed (°C), as stored in the printer (M145)
SAFE_OFF = 50          # °C: below it the hotend fan may stop without heat creep clogging the nozzle
READY_MARGIN = 3       # °C under the target that already counts as reached
MIN_EXTRUDE = 180      # °C: Marlin refuses to extrude colder than ~170 (cold extrusion protection)
KEEP_HOT = 20 * 60     # s: a nozzle left hot (cleaning, loading) cools down after this
HEAT_TIMEOUT = 10 * 60  # s: a heater that has not reached its target by then gives up
CONNECT_TIMEOUT = 2 * 60
RETRY_CONNECT = 15     # s between connection attempts while the printer's USB port is there
PURGE = ["M83", "G1 E50 F150"]                       # 50 mm slowly: old color out, new one flowing
UNLOAD = ["M83", "G1 E10 F300", "G1 E-100 F1800"]    # soften the tip, then pull back past the gears
COOL = ["M104 S0", "M140 S0", "M84"]                 # heaters and steppers off


# --- OctoPrint and Home Bridge -------------------------------------------------------------------

def octoprint(method, path, body=None):
    headers = {"X-Api-Key": os.environ.get("OCTOPRINT_API_KEY", "")}
    data = None
    if body is not None:
        data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
    request = urllib.request.Request(OCTOPRINT_URL + path, data=data, method=method, headers=headers)
    with urllib.request.urlopen(request, timeout=8) as response:
        raw = response.read()
    return json.loads(raw) if raw else {}


def gcode(commands):
    octoprint("POST", "/api/printer/command", {"commands": commands})


def read():
    """(printer, job): printer is None while OctoPrint is not connected to it (off or unplugged)."""
    try:
        printer = octoprint("GET", "/api/printer?exclude=sd")
    except urllib.error.HTTPError as error:
        if error.code != 409:  # 409: "Printer is not operational"
            raise
        printer = None
    return printer, octoprint("GET", "/api/job")


def bridge_power(on):
    request = urllib.request.Request(f"{BRIDGE_URL}/devices/{POWER_SWITCH}/{'on' if on else 'off'}", method="POST",
                                     headers={"Authorization": f"Bearer {os.environ.get('BRIDGE_API_KEY', '')}"})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read())


# --- shared intent ---------------------------------------------------------------------------------

def load_state(path=None):
    try:
        with open(path or STATE_PATH) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(state, path=None):
    path = path or STATE_PATH
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path))
    with os.fdopen(fd, "w") as f:
        json.dump(state, f)
    os.chmod(tmp, 0o660)  # Hermes writes it, the voice gateway (group 10000) carries it out
    os.replace(tmp, path)


def set_intent(intent, path=None):
    state = load_state(path)
    state["intent"] = intent
    save_state(state, path)


# --- reading the printer ---------------------------------------------------------------------------

def temp(printer, heater="tool0"):
    t = (printer or {}).get("temperature", {}).get(heater) or {}
    return t.get("actual") or 0.0, t.get("target") or 0.0


def busy(printer):
    flags = (printer or {}).get("state", {}).get("flags", {})
    return bool(flags.get("printing") or flags.get("paused") or flags.get("pausing"))


def duration(seconds):
    minutes = round((seconds or 0) / 60)
    return f"{minutes // 60} h {minutes % 60} min" if minutes >= 60 else f"{minutes} min"


def status(printer, job):
    if printer is None:
        return "La impresora no está conectada a OctoPrint; seguramente está apagada."
    nozzle, nozzle_target = temp(printer)
    bed, bed_target = temp(printer, "bed")
    temps = f"Boquilla a {nozzle:.0f} °C (objetivo {nozzle_target:.0f}), cama a {bed:.0f} °C (objetivo {bed_target:.0f})."
    if not busy(printer):
        return f"{printer['state']['text']}. {temps}"
    progress = job.get("progress") or {}
    name = ((job.get("job") or {}).get("file") or {}).get("display") or "la pieza"
    left = progress.get("printTimeLeft")
    left = f"le faltan unos {duration(left)}" if left else "aún no sé cuánto le falta"
    return f"Imprimiendo {name}: {progress.get('completion') or 0:.0f} %, {left}. {temps}"


# --- orders (Hermes tool) --------------------------------------------------------------------------

def material_temps(params):
    material = (params.get("material") or "pla").lower()
    if material not in MATERIALS:
        raise ValueError(f"Material desconocido: {material}. Disponibles: {', '.join(MATERIALS)}")
    return material, *MATERIALS[material]


def run(params, now=None):
    now = time.time() if now is None else now
    action = params.get("action")
    printer, job = read()
    if action == "status":
        return status(printer, job)
    if action == "power_on":
        bridge_power(True)
        set_intent({"do": "connect", "since": now})
        return "Encendí la impresora; en cuanto responda la conecto a OctoPrint y te aviso."
    if printer is None:
        raise RuntimeError("La impresora no está conectada a OctoPrint (¿apagada?). Puedo encenderla con power_on.")
    if busy(printer):
        raise RuntimeError("Está imprimiendo: no cambio temperaturas ni la apago hasta que termine. "
                           f"{status(printer, job)}")
    if action == "preheat":
        material, nozzle, bed = material_temps(params)
        gcode([f"M104 S{nozzle}", f"M140 S{bed}"])
        set_intent({"do": "preheat", "material": material, "nozzle": nozzle, "bed": bed, "since": now})
        return f"Precalentando para {material.upper()}: boquilla a {nozzle} °C y cama a {bed} °C. Te aviso cuando llegue."
    if action in ("load", "unload"):
        material, nozzle, _ = material_temps(params)
        gcode([f"M104 S{nozzle}"])
        set_intent({"do": action, "material": material, "nozzle": nozzle, "since": now})
        what = "meter" if action == "load" else "sacar"
        return f"Calentando la boquilla a {nozzle} °C para {what} el filamento. Te aviso cuando sea el momento."
    if action == "purge":
        nozzle, _ = temp(printer)
        if nozzle < MIN_EXTRUDE:
            raise RuntimeError(f"La boquilla está a {nozzle:.0f} °C: todavía no está caliente para purgar.")
        gcode(PURGE)
        set_intent({"do": "keep_hot", "until": now + KEEP_HOT})
        return "Purgando 50 mm. Cuando salga del color nuevo y limpio, retira el hilo de la boquilla."
    if action == "removed":
        nozzle, target = temp(printer)
        set_intent({"do": "keep_hot", "until": now + KEEP_HOT})
        return (f"Ahora toca limpiar la boquilla. La dejo caliente ({target:.0f} °C) {KEEP_HOT // 60} minutos; "
                "dime cuando termines y la enfrío.")
    if action == "cooldown":
        gcode(COOL)
        if params.get("power_off"):
            set_intent({"do": "power_off", "since": now})
            return f"Enfriando; la apago en cuanto la boquilla baje de {SAFE_OFF} °C."
        set_intent(None)
        return "Enfriando: apagué boquilla, cama y motores."
    if action == "power_off":
        gcode(COOL)
        set_intent({"do": "power_off", "since": now})
        return f"La apago en cuanto la boquilla baje de {SAFE_OFF} °C (ahora está a {temp(printer)[0]:.0f} °C)."
    raise ValueError("Acción no permitida")


# --- the watcher (voice gateway) -------------------------------------------------------------------

_last = {"job": None, "tried": float("-inf")}  # previous step's job state, last connect attempt


def autoconnect(now):
    """OctoPrint not connected but the printer's port is there (turned on by hand or from Home Assistant,
    or the USB dropped for a moment): connect. Off, the port is gone, so nothing is tried."""
    if now - _last["tried"] < RETRY_CONNECT:
        return
    _last["tried"] = now
    try:
        connection = octoprint("GET", "/api/connection")
        state, options = connection["current"]["state"], connection["options"]
        if state.startswith(("Closed", "Offline", "Error")) and options.get("portPreference") in options["ports"]:
            octoprint("POST", "/api/connection", {"command": "connect"})
    except Exception:
        pass


def power_off_now():
    try:
        octoprint("POST", "/api/connection", {"command": "disconnect"})  # no "serial error" when it dies
    except Exception:
        pass
    bridge_power(False)


def step(now=None, path=None):
    """Carry out the pending intent and watch the print. Returns what Finnip should say."""
    now = time.time() if now is None else now
    printer, job = read()
    state = load_state(path)
    intent = state.get("intent") or {}
    said = []

    def finish(message=None, next_intent=None):
        if message:
            said.append(message)
        state["intent"] = next_intent
        save_state(state, path)

    job_state, prev = job.get("state") or "", _last["job"]
    _last["job"] = job_state
    if prev is not None and job_state != prev:
        name = ((job.get("job") or {}).get("file") or {}).get("display") or "la pieza"
        if job_state.startswith("Printing") and not prev.startswith("Paus"):
            finish(None, None)  # a print takes over the heaters: drop "keep hot", "preheat"...
            intent = {}
        elif prev.startswith(("Printing", "Finishing")) and job_state.startswith("Operational"):
            gcode(COOL)
            finish(f"Terminó la impresión de {name}. La estoy enfriando y la apago cuando la boquilla "
                   f"baje de {SAFE_OFF} °C.", {"do": "power_off", "since": now})
            return said
        elif prev == "Cancelling":
            said.append(f"Se canceló la impresión de {name}.")

    if printer is None:
        autoconnect(now)
    do = intent.get("do")
    if do == "connect":
        if printer is not None:
            finish("La impresora ya está encendida y conectada.")
        elif now - intent["since"] > CONNECT_TIMEOUT:
            finish("Encendí la impresora pero OctoPrint no logró conectarse. Revisa el cable USB.")
        return said
    if not do or printer is None or busy(printer):
        if do and printer is None and do != "connect":
            finish(None, None)  # it was turned off some other way
        return said

    nozzle, _ = temp(printer)
    bed, _ = temp(printer, "bed")
    if do == "power_off":
        if nozzle < SAFE_OFF:
            power_off_now()
            finish("Listo: la impresora ya se enfrió y la apagué.")
        return said
    if do == "keep_hot":
        if now > intent["until"]:
            gcode(COOL)
            finish(f"Pasaron {KEEP_HOT // 60} minutos con la boquilla caliente, así que la apagué.")
        return said
    if do in ("preheat", "load", "unload"):
        hot = nozzle >= intent["nozzle"] - READY_MARGIN
        if do == "preheat":
            hot = hot and bed >= intent["bed"] - READY_MARGIN
        if not hot:
            if now - intent["since"] > HEAT_TIMEOUT:
                gcode(COOL)
                finish(f"La impresora no llegó a la temperatura en {HEAT_TIMEOUT // 60} minutos; apagué los "
                       "calentadores por seguridad. Revisa el termistor o el calentador.")
            return said
        keep = {"do": "keep_hot", "until": now + KEEP_HOT}
        if do == "preheat":
            finish(f"Ya está precalentada para {intent['material'].upper()}.", keep)
        elif do == "load":
            finish(f"La boquilla ya está a {nozzle:.0f} °C: es momento de meter el filamento. Empújalo hasta "
                   "que sientas que llega a la boquilla y dime «ya lo metí» para purgar.", keep)
        else:
            gcode(UNLOAD)
            finish("Ya retraje el filamento: es momento de sacarlo. Jálalo con cuidado y avísame cuando "
                   "esté fuera.", keep)
    return said


# --- Hermes ----------------------------------------------------------------------------------------

SCHEMA = {
    "name": "finnip_printer",
    "description": (
        "Controla la impresora 3D del usuario (Creality Ender-3 V3 SE en OctoPrint). "
        "status: estado, temperaturas y, si imprime, avance y tiempo restante. Cambia a cada minuto: "
        "llámala cada vez que pregunten por la impresora, nunca repitas un estado de antes. "
        "preheat: precalentar boquilla y cama para material (pla o petg). "
        "load: calentar para meter filamento; Finnip avisa solo cuando es momento de meterlo. "
        "purge: cuando el usuario dice que ya metió el filamento, extruye 50 mm. "
        "unload: calentar y retraer el filamento; Finnip avisa solo cuando es momento de sacarlo. "
        "removed: cuando el usuario ya sacó el filamento; deja la boquilla caliente para limpiar. "
        "cooldown: apagar calentadores y motores (power_off true para además apagar la impresora al enfriar). "
        "power_on / power_off: encender, o apagar la impresora en cuanto la boquilla esté fría. "
        "Los avisos de 'ya está caliente', 'terminó la impresión' y 'la apagué' los da Finnip solo: "
        "no esperes ni consultes de nuevo, solo comunica la respuesta de la herramienta."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["status", "preheat", "load", "purge", "unload", "removed",
                                                  "cooldown", "power_on", "power_off"]},
            "material": {"type": "string", "enum": list(MATERIALS), "description": "Por defecto pla"},
            "power_off": {"type": "boolean", "description": "Solo con cooldown: apagar al enfriar"},
        },
        "required": ["action"],
    },
}


def handle(params, **kwargs):
    try:
        return json.dumps({"success": True, "action": params.get("action"), "result": run(params)}, ensure_ascii=False)
    except Exception as error:
        return json.dumps({"success": False, "error": str(error)}, ensure_ascii=False)


def register(ctx):
    ctx.register_tool(name="finnip_printer", toolset="finnip_printer", schema=SCHEMA, handler=handle)
