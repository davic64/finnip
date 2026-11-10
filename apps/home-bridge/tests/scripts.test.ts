import { describe, expect, it } from "vitest";
import { createHomeAssistantService } from "../src/services/home-assistant.js";
import { fakeHomeAssistant } from "./fake-ha.js";

const env = { HA_URL: "http://homeassistant:8123", HA_TOKEN: "test-token", BRIDGE_API_KEY: "a".repeat(32) };

describe("script editor config", () => {
    it("saves, reads back and deletes a script", async () => {
        const ha = fakeHomeAssistant({ entities: [], labeled: [] });
        const service = createHomeAssistantService(env, ha.fetchImpl);
        expect(await service.getScriptConfig("modo_lectura")).toBeUndefined();
        const config = {
            alias: "Modo lectura", description: "Finnip: sin música",
            sequence: [{ action: "light.turn_on", target: { entity_id: "light.lampara" }, data: { color_temp_kelvin: 2700 } }],
        };
        await service.saveScriptConfig("modo_lectura", config);
        expect(await service.getScriptConfig("modo_lectura")).toEqual(config);
        expect((await service.getState("script.modo_lectura")).attributes.friendly_name).toBe("Modo lectura");
        await service.deleteScriptConfig("modo_lectura");
        expect(await service.getScriptConfig("modo_lectura")).toBeUndefined();
    });

    it("still fails on other errors", async () => {
        const ha = fakeHomeAssistant({ entities: [], labeled: [], fail: () => new Response("", { status: 500 }) });
        await expect(createHomeAssistantService(env, ha.fetchImpl).getScriptConfig("modo_x")).rejects.toThrow(/HTTP 500/);
    });
});
