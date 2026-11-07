import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { buildApp } from "../src/app.js";
import { DEVICES, type DeviceCatalog } from "../src/devices.js";

const env = { HA_URL: "http://homeassistant:8123", HA_TOKEN: "test-token", BRIDGE_API_KEY: "a".repeat(32) };
const headers = { authorization: `Bearer ${env.BRIDGE_API_KEY}` };
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const catalog: DeviceCatalog = {
    ...DEVICES,
    fan: { entityId: "switch.ventilador", type: "switch", name: "Ventilador" },
};

let fetchMock: ReturnType<typeof vi.fn<typeof fetch>>;
let app: ReturnType<typeof buildApp>;
beforeEach(() => {
    fetchMock = vi.fn<typeof fetch>();
    app = buildApp({ env, fetchImpl: fetchMock, logger: false, devices: catalog });
});
afterEach(async () => { await app.close(); });

it("keeps every catalog type consistent with its entity domain", () => {
    for (const device of Object.values(DEVICES)) {
        expect(device.entityId.startsWith(`${device.type}.`)).toBe(true);
    }
});

it("serves catalog lights through /devices/:id", async () => {
    fetchMock.mockResolvedValueOnce(json({
        entity_id: "light.leds_monitores", state: "on", attributes: { brightness: 255, rgb_color: [0, 255, 0] },
    }));
    const response = await app.inject({ method: "GET", url: "/devices/monitorLeds", headers });
    expect(response.statusCode).toBe(200);
    expect(response.json()).toEqual({ name: "Leds Monitores", state: "on", brightness: 100, rgb_color: [0, 255, 0] });
});

it("switches a switch through its own domain and omits light attributes", async () => {
    fetchMock.mockResolvedValueOnce(json([]))
        .mockResolvedValueOnce(json({ entity_id: "switch.ventilador", state: "on", attributes: {} }));
    const response = await app.inject({ method: "POST", url: "/devices/fan/on", headers });
    expect(response.statusCode).toBe(200);
    expect(response.json()).toEqual({
        success: true, action: "turn_on", device: "Ventilador", confirmed: true,
        actual: { name: "Ventilador", state: "on" },
    });
    const [url, options] = fetchMock.mock.calls[0]!;
    expect(url).toBe(`${env.HA_URL}/api/services/switch/turn_on`);
    expect(JSON.parse(options?.body as string)).toEqual({ entity_id: "switch.ventilador" });
    expect(fetchMock.mock.calls[1]![0]).toBe(`${env.HA_URL}/api/states/switch.ventilador`);
});

it("rejects color on devices that are not lights", async () => {
    const response = await app.inject({ method: "POST", url: "/devices/fan/color", headers, payload: { rgb: [0, 0, 255] } });
    expect(response.statusCode).toBe(400);
    expect(response.json()).toEqual({ error: "Device does not support color" });
    expect(fetchMock).not.toHaveBeenCalled();
});

it.each(["unknown", "toString", "__proto__", "constructor"])("returns 404 for unknown device %s", async (id) => {
    for (const [method, suffix] of [["GET", ""], ["POST", "/on"], ["POST", "/off"], ["POST", "/color"]] as const) {
        const response = await app.inject({ method, url: `/devices/${id}${suffix}`, headers });
        expect(response.statusCode).toBe(404);
        expect(response.json()).toEqual({ error: "Unknown device" });
    }
    expect(fetchMock).not.toHaveBeenCalled();
});

it("does not trust a state for a different entity", async () => {
    fetchMock.mockResolvedValueOnce(json({ entity_id: "switch.otro", state: "on", attributes: {} }));
    const response = await app.inject({ method: "GET", url: "/devices/fan", headers });
    expect(response.statusCode).toBe(502);
});

it("requires authentication on catalog routes", async () => {
    const response = await app.inject({ method: "POST", url: "/devices/monitorLeds/off" });
    expect(response.statusCode).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
});
