import type { Device } from "../devices.js";
import type { BridgeEnv } from "../schemas/env.js";
import { stateSchema } from "../schemas/devices.js";

export interface DeviceState {
    name: string;
    state: string;
    // Only lights report these.
    brightness?: number | null;
    rgb_color?: number[] | null;
}

export function createHomeAssistantService(env: BridgeEnv, fetchImpl: typeof fetch = fetch) {
    async function callService(device: Device, service: "turn_on" | "turn_off", data: Record<string, unknown> = {}) {
        const response = await fetchImpl(`${env.HA_URL}/api/services/${device.type}/${service}`, {
            method: "POST",
            headers: { Authorization: `Bearer ${env.HA_TOKEN}`, "Content-Type": "application/json" },
            body: JSON.stringify({ entity_id: device.entityId, ...data }),
            signal: AbortSignal.timeout(5000),
        });
        if (!response.ok) throw new Error(`Home Assistant returned HTTP ${response.status}`);
    }

    async function getState(device: Device): Promise<DeviceState> {
        const response = await fetchImpl(`${env.HA_URL}/api/states/${device.entityId}`, {
            headers: { Authorization: `Bearer ${env.HA_TOKEN}` },
            signal: AbortSignal.timeout(5000),
        });
        if (!response.ok) throw new Error(`Home Assistant returned HTTP ${response.status}`);
        const parsed = stateSchema.safeParse(await response.json());
        if (!parsed.success || parsed.data.entity_id !== device.entityId) {
            throw new Error("Invalid Home Assistant state");
        }
        const base = { name: device.name, state: parsed.data.state };
        if (device.type !== "light") return base;
        const rawBrightness = parsed.data.attributes.brightness;
        return {
            ...base,
            brightness: rawBrightness == null ? null : Math.round(rawBrightness / 255 * 100),
            rgb_color: parsed.data.attributes.rgb_color ?? null,
        };
    }

    return { callService, getState };
}
export type HomeAssistantService = ReturnType<typeof createHomeAssistantService>;
