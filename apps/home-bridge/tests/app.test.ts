import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { buildApp } from "../src/app.js";

const env = { HA_URL: "http://homeassistant:8123", HA_TOKEN: "test-token", BRIDGE_API_KEY: "a".repeat(32) };
const headers = { authorization: `Bearer ${env.BRIDGE_API_KEY}` };
const state = (attributes: Record<string, unknown> = {}, power = "on") => ({
    entity_id: "light.leds_monitores", state: power,
    attributes: { brightness: 255, rgb_color: [146, 224, 255], ...attributes },
});
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

let fetchMock: ReturnType<typeof vi.fn<typeof fetch>>;
let app: ReturnType<typeof buildApp>;
beforeEach(() => {
    fetchMock = vi.fn<typeof fetch>();
    app = buildApp({ env, fetchImpl: fetchMock, logger: false });
});
afterEach(async () => { await app.close(); });

it("exposes health without authentication or contacting Home Assistant", async () => {
    const response = await app.inject({ method: "GET", url: "/health" });
    expect(response.statusCode).toBe(200);
    expect(response.json()).toEqual({ status: "ok", service: "finnip-home-bridge" });
    expect(fetchMock).not.toHaveBeenCalled();
});

it.each([
    ["GET", "/lights/monitores"], ["POST", "/lights/monitores/color"],
    ["POST", "/lights/monitores/on"], ["POST", "/lights/monitores/off"],
] as const)("protects %s %s", async (method, url) => {
    for (const authorization of [undefined, "Bearer wrong", `Bearer ${"b".repeat(32)}`]) {
        const response = await app.inject({ method, url, headers: authorization ? { authorization } : {} });
        expect(response.statusCode).toBe(401);
        expect(response.json()).toEqual({ error: "Unauthorized" });
    }
    expect(fetchMock).not.toHaveBeenCalled();
});

it("returns device state with brightness as a percentage", async () => {
    fetchMock.mockResolvedValueOnce(json(state({ brightness: 102 })));
    const response = await app.inject({ method: "GET", url: "/lights/monitores", headers });
    expect(response.statusCode).toBe(200);
    expect(response.json()).toEqual({ name: "Leds Monitores", state: "on", brightness: 40, rgb_color: [146, 224, 255] });
    const [url, options] = fetchMock.mock.calls[0]!;
    expect(url).toBe(`${env.HA_URL}/api/states/light.leds_monitores`);
    expect(options?.headers).toEqual({ Authorization: "Bearer test-token" });
    expect(options?.signal).toBeInstanceOf(AbortSignal);
});

it("returns null for absent optional attributes", async () => {
    fetchMock.mockResolvedValueOnce(json({ entity_id: "light.leds_monitores", state: "off", attributes: {} }));
    const response = await app.inject({ method: "GET", url: "/lights/monitores", headers });
    expect(response.json()).toEqual({ name: "Leds Monitores", state: "off", brightness: null, rgb_color: null });
});

it("confirms normalized sky blue and returns the actual reported RGB", async () => {
    fetchMock.mockResolvedValueOnce(json([])).mockResolvedValueOnce(json(state()));
    const response = await app.inject({ method: "POST", url: "/lights/monitores/color", headers, payload: { rgb: [135, 206, 235] } });
    expect(response.statusCode).toBe(200);
    expect(response.json()).toEqual({
        success: true, confirmed: true, requested: { rgb: [135, 206, 235], brightness: 100 },
        actual: { name: "Leds Monitores", state: "on", brightness: 100, rgb_color: [146, 224, 255] },
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const [url, options] = fetchMock.mock.calls[0]!;
    expect(url).toBe(`${env.HA_URL}/api/services/light/turn_on`);
    expect(options?.method).toBe("POST");
    expect(JSON.parse(options?.body as string)).toEqual({ entity_id: "light.leds_monitores", rgb_color: [135, 206, 235], brightness_pct: 100 });
    expect(fetchMock.mock.calls[1]![0]).toContain("/api/states/");
});

it.each([
    ["different color", state({ rgb_color: [255, 0, 0] })],
    ["different brightness", state({ brightness: 102 })],
    ["off", state({}, "off")],
    ["unavailable", state({}, "unavailable")],
    ["missing color", state({ rgb_color: null })],
])("does not confirm %s", async (_label, actual) => {
    fetchMock.mockResolvedValueOnce(json([])).mockResolvedValueOnce(json(actual));
    const response = await app.inject({ method: "POST", url: "/lights/monitores/color", headers, payload: { rgb: [135, 206, 235], brightness: 100 } });
    expect(response.statusCode).toBe(200);
    expect(response.json().confirmed).toBe(false);
});

it.each([
    {}, { rgb: [1, 2] }, { rgb: [-1, 0, 0] }, { rgb: [256, 0, 0] },
    { rgb: [1.5, 0, 0] }, { rgb: ["1", 0, 0] },
    { rgb: [1, 2, 3], brightness: 0 }, { rgb: [1, 2, 3], brightness: 101 },
    { rgb: [1, 2, 3], brightness: 40.5 },
])("rejects invalid color input %j before contacting HA", async (payload) => {
    const response = await app.inject({ method: "POST", url: "/lights/monitores/color", headers, payload });
    expect(response.statusCode).toBe(400);
    expect(response.json()).toEqual({ error: "Invalid color or brightness" });
    expect(fetchMock).not.toHaveBeenCalled();
});

it.each(["on", "off"] as const)("runs %s and returns the confirmed state", async (action) => {
    fetchMock.mockResolvedValueOnce(json([])).mockResolvedValueOnce(json(state({}, action)));
    const response = await app.inject({ method: "POST", url: `/lights/monitores/${action}`, headers });
    expect(response.statusCode).toBe(200);
    expect(response.json()).toEqual({
        success: true, action: `turn_${action}`, device: "Leds Monitores", confirmed: true,
        actual: { name: "Leds Monitores", state: action, brightness: 100, rgb_color: [146, 224, 255] },
    });
    const [url, options] = fetchMock.mock.calls[0]!;
    expect(url).toBe(`${env.HA_URL}/api/services/light/turn_${action}`);
    expect(JSON.parse(options?.body as string)).toEqual({ entity_id: "light.leds_monitores" });
    expect(fetchMock.mock.calls[1]![0]).toContain("/api/states/");
});

it.each([["on", "off"], ["off", "on"], ["on", "unavailable"]] as const)(
    "does not confirm %s when HA reports %s", async (action, reported) => {
        fetchMock.mockResolvedValueOnce(json([])).mockResolvedValueOnce(json(state({}, reported)));
        const response = await app.inject({ method: "POST", url: `/lights/monitores/${action}`, headers });
        expect(response.statusCode).toBe(200);
        expect(response.json().confirmed).toBe(false);
    });

describe("upstream failures", () => {
    it.each(["http", "network", "timeout", "schema", "json"])("handles %s errors without leaking details", async (failure) => {
        if (failure === "http") fetchMock.mockResolvedValueOnce(json({}, 401));
        if (failure === "network") fetchMock.mockRejectedValueOnce(new Error("private upstream details"));
        if (failure === "timeout") fetchMock.mockRejectedValueOnce(new DOMException("timeout", "TimeoutError"));
        if (failure === "schema") fetchMock.mockResolvedValueOnce(json({ entity_id: "light.other" }));
        if (failure === "json") fetchMock.mockResolvedValueOnce(new Response("invalid json"));
        const response = await app.inject({ method: "GET", url: "/lights/monitores", headers });
        expect(response.statusCode).toBe(502);
        expect(response.json()).toEqual({ error: "Unable to get device state" });
    });
    it.each(["color", "on", "off"])("handles failed %s commands", async (action) => {
        fetchMock.mockResolvedValueOnce(json({}, 503));
        const response = await app.inject({ method: "POST", url: `/lights/monitores/${action}`, headers,
            ...(action === "color" ? { payload: { rgb: [135, 206, 235] } } : {}) });
        expect(response.statusCode).toBe(502);
        expect(response.json().error).toBe(action === "color" ? "Unable to communicate with Home Assistant" : `Unable to turn ${action} device`);
        expect(fetchMock).toHaveBeenCalledTimes(1);
    });
    it("does not confirm a command if the subsequent state read fails", async () => {
        fetchMock.mockResolvedValueOnce(json([])).mockResolvedValueOnce(json({}, 503));
        const response = await app.inject({ method: "POST", url: "/lights/monitores/color", headers, payload: { rgb: [135, 206, 235] } });
        expect(response.statusCode).toBe(502);
        expect(response.json()).toEqual({ error: "Unable to communicate with Home Assistant" });
    });
    it.each(["on", "off"])("fails %s if the subsequent state read fails", async (action) => {
        fetchMock.mockResolvedValueOnce(json([])).mockResolvedValueOnce(json({}, 503));
        const response = await app.inject({ method: "POST", url: `/lights/monitores/${action}`, headers });
        expect(response.statusCode).toBe(502);
        expect(response.json()).toEqual({ error: `Unable to turn ${action} device` });
    });
});

it.each([
    { ...env, HA_URL: "invalid" }, { ...env, HA_TOKEN: "" }, { ...env, BRIDGE_API_KEY: "short" },
])("fails early on invalid configuration", (invalidEnv) => {
    expect(() => buildApp({ env: invalidEnv, logger: false })).toThrow();
});
