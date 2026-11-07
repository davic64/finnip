import { afterEach, describe, expect, it } from "vitest";
import { buildApp } from "../src/app.js";
import type { Entity } from "../src/devices.js";
import { fakeHomeAssistant, set } from "./fake-ha.js";

const env = { HA_URL: "http://homeassistant:8123", HA_TOKEN: "test-token", BRIDGE_API_KEY: "a".repeat(32) };
const headers = { authorization: `Bearer ${env.BRIDGE_API_KEY}` };

const entity = (entity_id: string, state: string, attributes: Record<string, unknown> = {}): Entity =>
    ({ entity_id, state, attributes });
const ENTITIES = [
    entity("light.leds_monitores", "on", {
        friendly_name: "Leds Monitores", supported_color_modes: ["color_temp", "rgb"],
        brightness: 255, rgb_color: [146, 224, 255],
    }),
    entity("light.lampara", "off", { friendly_name: "Lámpara", supported_color_modes: ["brightness"] }),
    entity("light.foco", "off", { supported_color_modes: ["onoff"] }),
    entity("switch.ventilador", "off", { friendly_name: "Ventilador" }),
    entity("cover.persiana", "closed", { friendly_name: "Persiana", supported_features: 15, current_position: 0 }),
    entity("cover.garage", "closed", { supported_features: 3 }),
    entity("climate.aire", "cool", {
        friendly_name: "Aire", supported_features: 1, hvac_modes: ["off", "cool", "heat"],
        min_temp: 16, max_temp: 30, temperature: 24, current_temperature: 26,
    }),
    entity("lock.puerta", "locked"),
    entity("switch.mic_enable", "off"),
];
const LABELED = [
    "light.leds_monitores", "light.lampara", "light.foco", "switch.ventilador",
    "cover.persiana", "cover.garage", "climate.aire", "lock.puerta",
];

let app: ReturnType<typeof buildApp> | undefined;
afterEach(async () => { await app?.close(); app = undefined; });

function setup(options: Partial<Parameters<typeof fakeHomeAssistant>[0]> = {}) {
    const ha = fakeHomeAssistant({ entities: ENTITIES, labeled: LABELED, ...options });
    app = buildApp({ env, fetchImpl: ha.fetchImpl, logger: false });
    return { ha, app };
}

it("exposes health without authentication or contacting Home Assistant", async () => {
    const { ha, app } = setup();
    const response = await app.inject({ method: "GET", url: "/health" });
    expect(response.statusCode).toBe(200);
    expect(response.json()).toEqual({ status: "ok", service: "finnip-home-bridge" });
    expect(ha.calls).toHaveLength(0);
});

it.each([
    ["GET", "/devices"], ["GET", "/devices/light.leds_monitores"], ["POST", "/devices/light.leds_monitores/off"],
    ["GET", "/lights/monitores"], ["POST", "/lights/monitores/off"],
] as const)("protects %s %s", async (method, url) => {
    const { ha, app } = setup();
    for (const authorization of [undefined, "Bearer wrong", `Bearer ${"b".repeat(32)}`]) {
        const response = await app.inject({ method, url, headers: authorization ? { authorization } : {} });
        expect(response.statusCode).toBe(401);
        expect(response.json()).toEqual({ error: "Unauthorized" });
    }
    expect(ha.calls).toHaveLength(0);
});

describe("discovery", () => {
    it("lists only labeled entities of allowed domains, with their capabilities", async () => {
        const { ha, app } = setup();
        const response = await app.inject({ method: "GET", url: "/devices", headers });
        expect(response.statusCode).toBe(200);
        const devices = response.json().devices as { id: string; capabilities: string[] }[];
        expect(Object.fromEntries(devices.map((device) => [device.id, device.capabilities]))).toEqual({
            "light.leds_monitores": ["on", "off", "brightness", "color"],
            "light.lampara": ["on", "off", "brightness"],
            "light.foco": ["on", "off"],
            "switch.ventilador": ["on", "off"],
            "cover.persiana": ["open", "close", "position", "stop"],
            "cover.garage": ["open", "close"],
            "climate.aire": ["temperature", "hvac_mode"],
        });
        const template = ha.calls.find((call) => call.path === "/api/template")!;
        expect(template.body).toEqual({ template: "{{ label_entities('finnip') | tojson }}" });
    });

    it("describes each domain with its own attributes", async () => {
        const { app } = setup();
        const get = async (id: string) => (await app.inject({ method: "GET", url: `/devices/${id}`, headers })).json();
        expect(await get("light.leds_monitores")).toEqual({
            id: "light.leds_monitores", name: "Leds Monitores", domain: "light", state: "on",
            capabilities: ["on", "off", "brightness", "color"], brightness: 100, rgb_color: [146, 224, 255],
        });
        expect(await get("light.foco")).toMatchObject({ name: "light.foco", brightness: null, rgb_color: null });
        expect(await get("switch.ventilador")).toEqual({
            id: "switch.ventilador", name: "Ventilador", domain: "switch", state: "off", capabilities: ["on", "off"],
        });
        expect(await get("cover.persiana")).toMatchObject({ current_position: 0 });
        expect(await get("climate.aire")).toMatchObject({
            state: "cool", temperature: 24, current_temperature: 26, min_temp: 16, max_temp: 30,
            hvac_modes: ["off", "cool", "heat"],
        });
    });

    it("converts brightness to a percentage", async () => {
        const { app } = setup({ entities: [entity("light.leds_monitores", "on", { brightness: 102 })] });
        const response = await app.inject({ method: "GET", url: "/devices/light.leds_monitores", headers });
        expect(response.json().brightness).toBe(40);
    });

    it.each([
        ["unlabeled", "switch.mic_enable"], ["labeled but not an allowed domain", "lock.puerta"],
        ["absent", "light.nope"], ["malformed", "LIGHT.Foco"], ["malformed", "toString"],
        ["malformed", "__proto__"], ["malformed", "light.foco%2F..%2Fx"],
    ])("hides %s entity %s", async (_label, id) => {
        const { ha, app } = setup();
        for (const [method, suffix] of [["GET", ""], ["POST", "/on"]] as const) {
            const response = await app.inject({ method, url: `/devices/${id}${suffix}`, headers });
            expect(response.statusCode).toBe(404);
            expect(response.json()).toEqual({ error: "Unknown device" });
        }
        expect(ha.calls.filter((call) => call.path !== "/api/template")).toHaveLength(0);
    });
});

describe("actions", () => {
    it("confirms normalized sky blue and returns the actual reported RGB", async () => {
        const { ha, app } = setup({
            onService: (_d, _s, _b, entities) => set(entities, "light.leds_monitores", "on", { rgb_color: [146, 224, 255], brightness: 255 }),
        });
        const response = await app.inject({
            method: "POST", url: "/devices/light.leds_monitores/color", headers, payload: { rgb: [135, 206, 235] },
        });
        expect(response.statusCode).toBe(200);
        expect(response.json()).toMatchObject({
            success: true, action: "color", device: "Leds Monitores", confirmed: true,
            requested: { rgb: [135, 206, 235], brightness: 100 },
            actual: { state: "on", brightness: 100, rgb_color: [146, 224, 255] },
        });
        expect(ha.serviceCalls()).toEqual([expect.objectContaining({
            path: "/api/services/light/turn_on",
            body: { entity_id: "light.leds_monitores", rgb_color: [135, 206, 235], brightness_pct: 100 },
        })]);
    });

    it.each([
        ["different color", "on", { rgb_color: [255, 0, 0] }],
        ["different brightness", "on", { brightness: 102 }],
        ["off", "off", {}],
        ["unavailable", "unavailable", {}],
        ["missing color", "on", { rgb_color: null }],
    ])("does not confirm color when the light reports %s", async (_label, state, attributes) => {
        const { app } = setup({ onService: (_d, _s, _b, entities) => set(entities, "light.leds_monitores", state, attributes) });
        const response = await app.inject({
            method: "POST", url: "/devices/light.leds_monitores/color", headers, payload: { rgb: [135, 206, 235] },
        });
        expect(response.json().confirmed).toBe(false);
    });

    it.each([
        ["light.foco", "on", "/api/services/light/turn_on"],
        ["light.leds_monitores", "off", "/api/services/light/turn_off"],
        ["switch.ventilador", "on", "/api/services/switch/turn_on"],
    ])("turns %s %s through its own domain without a body", async (id, power, path) => {
        const { ha, app } = setup({ onService: (_d, _s, _b, entities) => set(entities, id, power) });
        const response = await app.inject({ method: "POST", url: `/devices/${id}/${power}`, headers });
        expect(response.statusCode).toBe(200);
        expect(response.json()).toMatchObject({ success: true, action: power, confirmed: true, actual: { state: power } });
        expect(response.json()).not.toHaveProperty("requested");
        expect(ha.serviceCalls()).toEqual([expect.objectContaining({ path, body: { entity_id: id } })]);
    });

    it("does not confirm power when HA reports another state", async () => {
        const { app } = setup({ onService: (_d, _s, _b, entities) => set(entities, "switch.ventilador", "unavailable") });
        const response = await app.inject({ method: "POST", url: "/devices/switch.ventilador/on", headers });
        expect(response.json().confirmed).toBe(false);
    });

    it("sets brightness on a dimmable light", async () => {
        const { ha, app } = setup({ onService: (_d, _s, _b, entities) => set(entities, "light.lampara", "on", { brightness: 128 }) });
        const response = await app.inject({
            method: "POST", url: "/devices/light.lampara/brightness", headers, payload: { brightness: 50 },
        });
        expect(response.json()).toMatchObject({ confirmed: true, actual: { brightness: 50 } });
        expect(ha.serviceCalls()[0]!.body).toEqual({ entity_id: "light.lampara", brightness_pct: 50 });
    });

    it("moves a cover and confirms its position", async () => {
        const { ha, app } = setup({ onService: (_d, _s, _b, entities) => set(entities, "cover.persiana", "open", { current_position: 50 }) });
        const response = await app.inject({
            method: "POST", url: "/devices/cover.persiana/position", headers, payload: { position: 50 },
        });
        expect(response.json()).toMatchObject({ confirmed: true, actual: { current_position: 50 } });
        expect(ha.serviceCalls()).toEqual([expect.objectContaining({
            path: "/api/services/cover/set_cover_position", body: { entity_id: "cover.persiana", position: 50 },
        })]);
    });

    it.each([["open", "opening", true], ["close", "closing", true], ["stop", "open", true], ["open", "closed", false]])(
        "cover %s reported as %s is confirmed=%s", async (action, state, confirmed) => {
            const { ha, app } = setup({ onService: (_d, _s, _b, entities) => set(entities, "cover.persiana", state) });
            const response = await app.inject({ method: "POST", url: `/devices/cover.persiana/${action}`, headers });
            expect(response.json().confirmed).toBe(confirmed);
            expect(ha.serviceCalls()[0]!.path).toBe(`/api/services/cover/${action}_cover`);
        });

    it("sets climate temperature and mode within device limits", async () => {
        const { ha, app } = setup({
            onService: (_d, service, body, entities) => service === "set_temperature"
                ? set(entities, "climate.aire", "cool", { temperature: body.temperature })
                : set(entities, "climate.aire", String(body.hvac_mode)),
        });
        const temperature = await app.inject({
            method: "POST", url: "/devices/climate.aire/temperature", headers, payload: { temperature: 22.5 },
        });
        expect(temperature.json()).toMatchObject({ confirmed: true, actual: { temperature: 22.5 } });
        const mode = await app.inject({
            method: "POST", url: "/devices/climate.aire/hvac_mode", headers, payload: { hvac_mode: "heat" },
        });
        expect(mode.json()).toMatchObject({ confirmed: true, actual: { state: "heat" } });
        expect(ha.serviceCalls().map((call) => call.path)).toEqual([
            "/api/services/climate/set_temperature", "/api/services/climate/set_hvac_mode",
        ]);
    });

    it.each([
        [{ temperature: 35 }, "temperature", "Temperature must be between 16 and 30"],
        [{ temperature: 10 }, "temperature", "Temperature must be between 16 and 30"],
        [{ hvac_mode: "dry" }, "hvac_mode", "Unsupported HVAC mode"],
    ])("rejects %j outside climate limits", async (payload, action, error) => {
        const { ha, app } = setup();
        const response = await app.inject({ method: "POST", url: `/devices/climate.aire/${action}`, headers, payload });
        expect(response.statusCode).toBe(400);
        expect(response.json()).toEqual({ error });
        expect(ha.serviceCalls()).toHaveLength(0);
    });

    it.each([
        ["switch.ventilador", "color", { rgb: [0, 0, 255] }], ["light.foco", "color", { rgb: [0, 0, 255] }],
        ["light.foco", "brightness", { brightness: 50 }], ["cover.garage", "position", { position: 10 }],
        ["cover.garage", "stop", {}], ["light.leds_monitores", "temperature", { temperature: 20 }],
        ["climate.aire", "on", {}],
    ])("rejects %s %s because the device lacks the capability", async (id, action, payload) => {
        const { ha, app } = setup();
        const response = await app.inject({ method: "POST", url: `/devices/${id}/${action}`, headers, payload });
        expect(response.statusCode).toBe(400);
        expect(response.json()).toEqual({ error: "Action not supported by this device" });
        expect(ha.serviceCalls()).toHaveLength(0);
    });

    it.each(["explode", "toString", "__proto__"])("returns 404 for unknown action %s without contacting HA", async (action) => {
        const { ha, app } = setup();
        const response = await app.inject({ method: "POST", url: `/devices/light.leds_monitores/${action}`, headers });
        expect(response.statusCode).toBe(404);
        expect(response.json()).toEqual({ error: "Unknown action" });
        expect(ha.calls).toHaveLength(0);
    });

    it.each([
        ["color", {}], ["color", { rgb: [1, 2] }], ["color", { rgb: [-1, 0, 0] }], ["color", { rgb: [256, 0, 0] }],
        ["color", { rgb: [1.5, 0, 0] }], ["color", { rgb: ["1", 0, 0] }],
        ["color", { rgb: [1, 2, 3], brightness: 0 }], ["color", { rgb: [1, 2, 3], brightness: 101 }],
        ["color", { rgb: [1, 2, 3], brightness: 40.5 }], ["brightness", { brightness: "50" }],
        ["position", { position: 101 }], ["temperature", { temperature: "22" }], ["hvac_mode", { hvac_mode: "" }],
    ])("rejects invalid %s input %j before contacting HA", async (action, payload) => {
        const { ha, app } = setup();
        const response = await app.inject({ method: "POST", url: `/devices/light.leds_monitores/${action}`, headers, payload });
        expect(response.statusCode).toBe(400);
        expect(response.json()).toEqual({ error: "Invalid input for action" });
        expect(ha.calls).toHaveLength(0);
    });
});

describe("upstream failures", () => {
    const unavailable = { error: "Unable to communicate with Home Assistant" };

    it.each([
        ["template HTTP error", (_m: string, path: string) => path === "/api/template" ? new Response("", { status: 500 }) : undefined],
        ["state HTTP error", (_m: string, path: string) => path.startsWith("/api/states") ? new Response("", { status: 401 }) : undefined],
        ["network error", () => { throw new Error("private upstream details"); }],
        ["timeout", () => { throw new DOMException("timeout", "TimeoutError"); }],
        ["invalid JSON", (_m: string, path: string) => path.startsWith("/api/states") ? new Response("invalid json") : undefined],
        ["invalid schema", (_m: string, path: string) => path.startsWith("/api/states") ? new Response(JSON.stringify({ entity_id: 1 })) : undefined],
    ])("returns 502 without leaking details on %s", async (_label, fail) => {
        const { app } = setup({ fail });
        for (const url of ["/devices", "/devices/light.leds_monitores"]) {
            const response = await app.inject({ method: "GET", url, headers });
            expect(response.statusCode).toBe(502);
            expect(response.json()).toEqual(unavailable);
        }
    });

    it("rejects a state that belongs to another entity", async () => {
        const { app } = setup({
            fail: (_m, path) => path.startsWith("/api/states/") ? new Response(JSON.stringify(entity("light.otro", "on"))) : undefined,
        });
        const response = await app.inject({ method: "GET", url: "/devices/light.leds_monitores", headers });
        expect(response.statusCode).toBe(502);
    });

    it("returns 502 when the service call fails, without retrying", async () => {
        const { ha, app } = setup({ fail: (_m, path) => path.startsWith("/api/services/") ? new Response("", { status: 503 }) : undefined });
        const response = await app.inject({ method: "POST", url: "/devices/light.leds_monitores/off", headers });
        expect(response.statusCode).toBe(502);
        expect(response.json()).toEqual(unavailable);
        expect(ha.serviceCalls()).toHaveLength(1);
    });

    it("does not confirm a command if the state read after it fails", async () => {
        let served = 0;
        const { app } = setup({
            fail: (method, path) => method === "GET" && path.startsWith("/api/states/") && served++ > 0
                ? new Response("", { status: 503 }) : undefined,
        });
        const response = await app.inject({ method: "POST", url: "/devices/light.leds_monitores/off", headers });
        expect(response.statusCode).toBe(502);
        expect(response.json()).toEqual(unavailable);
    });
});

describe("legacy /lights/monitores routes", () => {
    it("map to light.leds_monitores", async () => {
        const { ha, app } = setup({ onService: (_d, _s, _b, entities) => set(entities, "light.leds_monitores", "off") });
        const state = await app.inject({ method: "GET", url: "/lights/monitores", headers });
        const direct = await app.inject({ method: "GET", url: "/devices/light.leds_monitores", headers });
        expect(state.json()).toEqual(direct.json());
        const off = await app.inject({ method: "POST", url: "/lights/monitores/off", headers });
        expect(off.json()).toMatchObject({ action: "off", confirmed: true });
        expect(ha.serviceCalls()[0]!.path).toBe("/api/services/light/turn_off");
    });

    it("still require the Finnip label", async () => {
        const { app } = setup({ labeled: [] });
        const response = await app.inject({ method: "GET", url: "/lights/monitores", headers });
        expect(response.statusCode).toBe(404);
    });
});

it("sends the HA token, and a JSON content type only with a body", async () => {
    const { ha, app } = setup();
    await app.inject({ method: "POST", url: "/devices/switch.ventilador/on", headers });
    const read = ha.calls.find((call) => call.method === "GET")!;
    const command = ha.serviceCalls()[0]!;
    expect(read.headers).toEqual({ Authorization: "Bearer test-token" });
    expect(command.headers).toEqual({ Authorization: "Bearer test-token", "Content-Type": "application/json" });
});

it.each([
    { ...env, HA_URL: "invalid" }, { ...env, HA_TOKEN: "" }, { ...env, BRIDGE_API_KEY: "short" },
])("fails early on invalid configuration", (invalidEnv) => {
    expect(() => buildApp({ env: invalidEnv, logger: false })).toThrow();
});
