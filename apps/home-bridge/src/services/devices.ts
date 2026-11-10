import { findAction, type ActionName } from "../actions.js";
import { DEVICE_LABEL, domainOf, toDevice, type Device, type Domain } from "../devices.js";
import type { HomeAssistantService } from "./home-assistant.js";
import { MUSIC_OFF } from "../modes.js";

// ponytail: no cache, every request asks HA for the label (one extra local call); cache if it ever gets slow.
// Some devices (Alexa) report a new state a moment after the command: re-read until it matches,
// for up to SETTLE_TRIES * settleMs, so callers get the real state instead of a stale one.
const SETTLE_TRIES = 8;
const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
export function createDevicesService(homeAssistant: HomeAssistantService, settleMs = 500) {
    async function exposedIds() {
        const ids = await homeAssistant.labeledEntityIds(DEVICE_LABEL);
        return new Set(ids.filter((id) => domainOf(id)));
    }

    async function read(id: string, domain: Domain) {
        return withMusic(toDevice(await homeAssistant.getState(id), domain));
    }

    // ponytail: one local config read per exposed script on every list; cache it if modes multiply.
    async function withMusic(device: Device): Promise<Device> {
        if (device.domain !== "script") return device;
        const config = await homeAssistant.getScriptConfig(device.id.slice("script.".length));
        return { ...device, music: config?.description?.trim() !== MUSIC_OFF };
    }

    return {
        async list(): Promise<Device[]> {
            const [ids, entities] = await Promise.all([exposedIds(), homeAssistant.getStates()]);
            return Promise.all(entities
                .filter((entity) => ids.has(entity.entity_id))
                .map((entity) => withMusic(toDevice(entity, domainOf(entity.entity_id)!))));
        },

        // undefined when the entity is not labeled for Finnip or its domain is not allowed.
        async get(id: string): Promise<Device | undefined> {
            const domain = domainOf(id);
            if (!domain || !(await exposedIds()).has(id)) return undefined;
            return read(id, domain);
        },

        // Read back after the command so callers see what HA reports, not just what was sent.
        async run(device: Device, name: ActionName, input: Record<string, unknown>) {
            const action = findAction(name)!;
            await homeAssistant.callService(device.domain, action.service, {
                entity_id: device.id,
                ...action.data?.(input),
            });
            let actual = await read(device.id, device.domain);
            for (let i = 0; i < SETTLE_TRIES && !action.confirm(input, actual, device); i++) {
                await sleep(settleMs);
                // Alexa only polls Amazon now and then: ask for a fresh read instead of waiting for it.
                if (device.domain === "media_player") {
                    await homeAssistant.callService("homeassistant", "update_entity", { entity_id: device.id }).catch(() => {});
                }
                actual = await read(device.id, device.domain);
            }
            return {
                success: true,
                action: name,
                device: device.name,
                confirmed: action.confirm(input, actual, device),
                ...(Object.keys(input).length > 0 ? { requested: input } : {}),
                actual,
            };
        },
    };
}
export type DevicesService = ReturnType<typeof createDevicesService>;
