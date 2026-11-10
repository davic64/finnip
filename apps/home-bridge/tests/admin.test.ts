import { afterEach, describe, expect, it } from "vitest";
import { buildApp } from "../src/app.js";
import type { Entity } from "../src/devices.js";
import { fromHa, readMode, toHa } from "../src/modes.js";
import { RegistryError, type Registry } from "../src/services/registry.js";
import { fakeHomeAssistant } from "./fake-ha.js";

const env = { HA_URL: "http://homeassistant:8123", HA_TOKEN: "test-token", BRIDGE_API_KEY: "a".repeat(32) };
const headers = { authorization: `Bearer ${env.BRIDGE_API_KEY}` };
const entity = (entity_id: string, state: string, attributes: Record<string, unknown> = {}): Entity =>
    ({ entity_id, state, attributes });

const LAMP = entity("light.lampara", "off", {
    friendly_name: "Lámpara", supported_color_modes: ["color_temp", "hs"], min_color_temp_kelvin: 2000, max_color_temp_kelvin: 6500,
});
const LEDS = entity("light.leds_monitores", "on", { friendly_name: "Leds Monitores", supported_color_modes: ["rgb"] });
const ECHO = entity("media_player.habitacion_echo_dave", "idle", { friendly_name: "Echo Dave", volume_level: 0.3 });
const NEW_LAMP = entity("light.lampara_buro", "off", { friendly_name: "Lámpara del buró", supported_color_modes: ["brightness"] });
const DOOR = entity("lock.puerta_principal", "locked", { friendly_name: "Puerta principal" });
const SPEAKER_SWITCH = entity("switch.echo_dave_no_molestar", "off", { friendly_name: "Echo Dave No molestar" });

// The user's four modes before they were deleted (scripts.yaml backup), as the script editor returns them.
const step = (action: string, entity_id: string, data?: Record<string, unknown>) =>
    ({ action, target: { entity_id }, ...(data ? { data } : {}), continue_on_error: true });
const OLD_MODES: Record<string, { alias: string; description: string; sequence: Record<string, unknown>[] }> = {
    modo_estudio: { alias: "Modo estudio", description: "Finnip: con música", sequence: [
        step("light.turn_on", "light.lampara", { rgb_color: [255, 244, 229], brightness_pct: 100 }),
        step("light.turn_on", "light.leds_monitores", { rgb_color: [0, 120, 255], brightness_pct: 40 }),
        step("media_player.volume_set", "media_player.habitacion_echo_dave", { volume_level: 0.25 }),
    ] },
    modo_trabajo_profundo: { alias: "Modo trabajo profundo", description: "Finnip: con música", sequence: [
        step("light.turn_on", "light.lampara", { rgb_color: [255, 236, 210], brightness_pct: 70 }),
        step("light.turn_on", "light.leds_monitores", { rgb_color: [0, 230, 255], brightness_pct: 15 }),
        step("media_player.volume_set", "media_player.habitacion_echo_dave", { volume_level: 0.2 }),
    ] },
    modo_cine: { alias: "Modo cine", description: "Finnip: sin música", sequence: [
        step("light.turn_off", "light.lampara"),
        step("light.turn_on", "light.leds_monitores", { rgb_color: [60, 0, 255], brightness_pct: 10 }),
        step("media_player.media_pause", "media_player.habitacion_echo_dave"),
    ] },
    modo_calido: { alias: "Modo cálido", description: "Finnip: con música", sequence: [
        step("light.turn_on", "light.lampara", { color_temp_kelvin: 2630, brightness_pct: 60 }),
        step("light.turn_on", "light.leds_monitores", { rgb_color: [255, 90, 20], brightness_pct: 30 }),
        step("media_player.volume_set", "media_player.habitacion_echo_dave", { volume_level: 0.3 }),
    ] },
};

/** Labels in memory, shared with the fake's label template (the same `labeled` array). */
function fakeRegistry(labeled: string[], unregistered: string[] = []) {
    const labels = new Map<string, string[]>(labeled.map((id) => [id, ["finnip"]]));
    const registry: Registry = {
        async getLabels(id) {
            if (unregistered.includes(id)) throw new RegistryError("Entity not found", "not_found");
            return labels.get(id) ?? [];
        },
        async setLabels(id, next) {
            labels.set(id, next);
            const i = labeled.indexOf(id);
            if (next.includes("finnip") && i < 0) labeled.push(id);
            if (!next.includes("finnip") && i >= 0) labeled.splice(i, 1);
        },
    };
    return { registry, labels };
}

let app: ReturnType<typeof buildApp> | undefined;
afterEach(async () => { await app?.close(); app = undefined; });

function setup(options: { scripts?: Record<string, Record<string, unknown>>; unregistered?: string[]; entities?: Entity[] } = {}) {
    const labeled = ["light.lampara", "light.leds_monitores", "media_player.habitacion_echo_dave"];
    const ha = fakeHomeAssistant({
        entities: options.entities ?? [LAMP, LEDS, ECHO, NEW_LAMP, DOOR, SPEAKER_SWITCH], labeled, scripts: options.scripts,
    });
    const { registry, labels } = fakeRegistry(labeled, options.unregistered);
    app = buildApp({ env, fetchImpl: ha.fetchImpl, logger: false, settleMs: 0, registry, labelWaitMs: 0 });
    return { ha, app, labels, labeled };
}

describe("mode steps translation", () => {
    it.each(Object.entries(OLD_MODES))("reads %s as editable and writes back the same steps", (id, config) => {
        const mode = readMode(id.slice(5), config);
        expect(mode.editable).toBe(true);
        expect(mode.music).toBe(id !== "modo_cine");
        const devices = { "light.lampara": "light", "light.leds_monitores": "light", "media_player.habitacion_echo_dave": "media_player" };
        const back = mode.steps!.map((s) => toHa(s, { id: s.device, domain: devices[s.device as keyof typeof devices] } as never));
        expect(back).toEqual(config.sequence);
    });

    it("marks hand-edited steps as not editable", () => {
        expect(fromHa({ delay: { seconds: 5 } })).toBeUndefined();
        expect(fromHa(step("shell_command.reboot", "shell_command.reboot"))).toBeUndefined();
        expect(fromHa(step("light.turn_on", "light.lampara", { effect: "colorloop" }))).toBeUndefined();
        expect(readMode("x", { sequence: [step("light.turn_off", "light.lampara"), { delay: 5 }] })).toMatchObject({ editable: false, steps: null });
    });
});

describe("device exposure", () => {
    it("lists unlabeled devices of allowed domains only", async () => {
        const { app } = setup();
        const { candidates } = (await app.inject({ method: "GET", url: "/candidates", headers })).json();
        expect(candidates.map((c: { id: string }) => c.id).sort()).toEqual(["light.lampara_buro", "switch.echo_dave_no_molestar"]);
        expect(candidates.find((c: { id: string }) => c.id === "light.lampara_buro")).toEqual(
            { id: "light.lampara_buro", name: "Lámpara del buró", domain: "light", state: "off" });
    });

    it("exposes a new lamp, keeping its other labels, and it can be controlled", async () => {
        const { app, labels } = setup();
        labels.set("light.lampara_buro", ["recamara"]);
        const exposed = await app.inject({ method: "POST", url: "/devices/light.lampara_buro/expose", headers });
        expect(exposed.json()).toMatchObject({ id: "light.lampara_buro", name: "Lámpara del buró" });
        expect(labels.get("light.lampara_buro")).toEqual(["recamara", "finnip"]);
        const on = await app.inject({ method: "POST", url: "/devices/light.lampara_buro/on", headers });
        expect(on.statusCode).toBe(200);
    });

    it("refuses a lock without touching Home Assistant", async () => {
        const { app, labels } = setup();
        const response = await app.inject({ method: "POST", url: "/devices/lock.puerta_principal/expose", headers });
        expect(response.statusCode).toBe(400);
        expect(labels.has("lock.puerta_principal")).toBe(false);
    });

    it("explains when the entity has no registry entry", async () => {
        const { app } = setup({ unregistered: ["light.lampara_buro"] });
        const response = await app.inject({ method: "POST", url: "/devices/light.lampara_buro/expose", headers });
        expect(response.statusCode).toBe(404);
        expect(response.json().error).toMatch(/registro/);
    });

    it("hides a device and names the modes that still use it", async () => {
        const { app, labeled } = setup({ scripts: { modo_cine: OLD_MODES.modo_cine! } });
        const response = await app.inject({ method: "POST", url: "/devices/light.lampara/hide", headers });
        expect(response.json()).toEqual({ id: "light.lampara", hidden: true, used_by_modes: ["Modo cine"] });
        expect(labeled).not.toContain("light.lampara");
        expect((await app.inject({ method: "GET", url: "/devices/light.lampara", headers })).statusCode).toBe(404);
    });
});

describe("modes", () => {
    const lectura = {
        name: "lectura", music: false, steps: [
            { device: "light.lampara", action: "color_temp", params: { kelvin: 2700, brightness: 40 } },
            { device: "light.leds_monitores", action: "off" },
        ],
    };

    it("creates a mode, labels it, and it can be run", async () => {
        const { app, ha, labeled } = setup();
        const saved = await app.inject({ method: "PUT", url: "/modes/lectura", headers, payload: lectura });
        expect(saved.statusCode).toBe(200);
        expect(saved.json()).toMatchObject({ slug: "lectura", name: "Modo lectura", music: false, editable: true });
        expect(ha.scripts.get("modo_lectura")).toEqual({
            alias: "Modo lectura", description: "Finnip: sin música", sequence: [
                step("light.turn_on", "light.lampara", { color_temp_kelvin: 2700, brightness_pct: 40 }),
                step("light.turn_off", "light.leds_monitores"),
            ],
        });
        expect(labeled).toContain("script.modo_lectura");
        const device = (await app.inject({ method: "GET", url: "/devices/script.modo_lectura", headers })).json();
        expect(device).toMatchObject({ capabilities: ["run"], music: false });
    });

    it("reads music from the script description, defaulting to music", async () => {
        const { app, labeled } = setup({ scripts: {
            modo_cine: OLD_MODES.modo_cine!, modo_viejo: { alias: "Modo viejo", sequence: [step("light.turn_off", "light.lampara")] },
        } });
        labeled.push("script.modo_cine", "script.modo_viejo");
        const { devices } = (await app.inject({ method: "GET", url: "/devices", headers })).json();
        const music = Object.fromEntries(devices.filter((d: { domain: string }) => d.domain === "script").map((d: { id: string; music: boolean }) => [d.id, d.music]));
        expect(music).toEqual({ "script.modo_cine": false, "script.modo_viejo": true });
    });

    it.each([
        ["a device that is not exposed", { device: "lock.puerta_principal", action: "off" }, /no expuesto/],
        ["an out of range value", { device: "light.lampara", action: "color_temp", params: { kelvin: 9000 } }, /2000 and 6500/],
        ["an action not allowed in modes", { device: "media_player.habitacion_echo_dave", action: "command", params: { text: "hola" } }, /no se permite/],
        ["an action the device lacks", { device: "light.leds_monitores", action: "color_temp", params: { kelvin: 2700 } }, /no soporta/],
    ])("refuses the whole mode for %s, naming the step", async (_label, bad, error) => {
        const { app, ha } = setup();
        const response = await app.inject({
            method: "PUT", url: "/modes/malo", headers,
            payload: { steps: [{ device: "light.lampara", action: "on" }, bad] },
        });
        expect(response.statusCode).toBe(400);
        expect(response.json().error).toMatch(/^Paso 2/);
        expect(response.json().error).toMatch(error);
        expect(ha.scripts.has("modo_malo")).toBe(false);
    });

    it("reads and changes one step, keeping the rest", async () => {
        const { app, ha } = setup({ scripts: { modo_estudio: OLD_MODES.modo_estudio! } });
        const mode = (await app.inject({ method: "GET", url: "/modes/estudio", headers })).json();
        mode.steps[0].params.brightness = 80;
        await app.inject({ method: "PUT", url: "/modes/estudio", headers, payload: { music: mode.music, steps: mode.steps } });
        const saved = ha.scripts.get("modo_estudio") as { alias: string; sequence: { data: unknown }[] };
        expect(saved.alias).toBe("Modo estudio");
        expect(saved.sequence[0]!.data).toEqual({ rgb_color: [255, 244, 229], brightness_pct: 80 });
        expect(saved.sequence.slice(1)).toEqual(OLD_MODES.modo_estudio!.sequence.slice(1));
    });

    it("does not overwrite a mode edited by hand", async () => {
        const manual = { alias: "Modo fiesta", sequence: [step("light.turn_on", "light.lampara"), { delay: { seconds: 10 } }] };
        const { app, ha } = setup({ scripts: { modo_fiesta: manual } });
        const response = await app.inject({
            method: "PUT", url: "/modes/fiesta", headers, payload: { steps: [{ device: "light.lampara", action: "off" }] },
        });
        expect(response.statusCode).toBe(409);
        expect(ha.scripts.get("modo_fiesta")).toEqual(manual);
    });

    it("lists modes and deletes only modo_ scripts", async () => {
        const { app, ha } = setup({ scripts: { modo_cine: OLD_MODES.modo_cine!, respaldo_nocturno: { alias: "Respaldo", sequence: [] } } });
        const { modes } = (await app.inject({ method: "GET", url: "/modes", headers })).json();
        expect(modes.map((m: { slug: string }) => m.slug)).toEqual(["cine"]);
        expect((await app.inject({ method: "DELETE", url: "/modes/cine", headers })).json()).toEqual({ slug: "cine", deleted: true });
        expect(ha.scripts.has("modo_cine")).toBe(false);
        expect((await app.inject({ method: "DELETE", url: "/modes/cine", headers })).statusCode).toBe(404);
        expect((await app.inject({ method: "DELETE", url: "/modes/..%2Frespaldo_nocturno", headers })).statusCode).toBe(400);
        expect(ha.scripts.has("respaldo_nocturno")).toBe(true);
    });
});
