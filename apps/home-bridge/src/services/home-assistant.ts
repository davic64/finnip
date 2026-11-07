import type { BridgeEnv } from "../schemas/env.js";
import { lightSchema } from "../schemas/lights.js";

export function createHomeAssistantService(env: BridgeEnv, fetchImpl: typeof fetch = fetch) {
    async function callService(service: "turn_on" | "turn_off", data: Record<string, unknown> = {}) {
        const response = await fetchImpl(`${env.HA_URL}/api/services/light/${service}`, {
            method: "POST",
            headers: { Authorization: `Bearer ${env.HA_TOKEN}`, "Content-Type": "application/json" },
            body: JSON.stringify({ entity_id: "light.leds_monitores", ...data }),
            signal: AbortSignal.timeout(5000),
        });
        if (!response.ok) throw new Error(`Home Assistant returned HTTP ${response.status}`);
    }

    async function getLightState() {
        const response = await fetchImpl(`${env.HA_URL}/api/states/light.leds_monitores`, {
            headers: { Authorization: `Bearer ${env.HA_TOKEN}` },
            signal: AbortSignal.timeout(5000),
        });
        if (!response.ok) throw new Error(`Home Assistant returned HTTP ${response.status}`);
        const parsed = lightSchema.safeParse(await response.json());
        if (!parsed.success) throw new Error("Invalid Home Assistant state");
        const rawBrightness = parsed.data.attributes.brightness;
        return {
            name: "Leds Monitores",
            state: parsed.data.state,
            brightness: rawBrightness == null ? null : Math.round(rawBrightness / 255 * 100),
            rgb_color: parsed.data.attributes.rgb_color ?? null,
        };
    }

    return { callService, getLightState };
}
export type HomeAssistantService = ReturnType<typeof createHomeAssistantService>;
