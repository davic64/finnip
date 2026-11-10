import { ALLOWED_DOMAINS, DEVICE_LABEL, domainOf } from "../devices.js";
import { checkStep, MUSIC_OFF, MUSIC_ON, readMode, scriptId, SLUG, toHa, type HaStep, type Mode } from "../modes.js";
import type { DevicesService } from "./devices.js";
import type { HomeAssistantService } from "./home-assistant.js";
import { RegistryError, type Registry } from "./registry.js";

// What Finnip may manage in Home Assistant by itself: which devices it sees (the "finnip" label, only
// these domains; scripts come in only as modes) and its modes (scripts modo_*). Nothing else.
export const EXPOSABLE_DOMAINS = ALLOWED_DOMAINS.filter((domain) => domain !== "script");
const LABEL_TRIES = 10; // a new script's registry entry appears after Home Assistant reloads
const LABEL_WAIT_MS = 200;

/** A request Home Bridge refuses (status + message for the caller), as opposed to Home Assistant failing. */
export class Refused extends Error {
    constructor(readonly status: number, message: string) {
        super(message);
    }
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export function createAdminService(
    homeAssistant: HomeAssistantService,
    registry: Registry,
    devices: DevicesService,
    labelWaitMs = LABEL_WAIT_MS,
) {
    function exposable(id: string) {
        const domain = domainOf(id);
        if (!domain || !EXPOSABLE_DOMAINS.includes(domain as (typeof EXPOSABLE_DOMAINS)[number])) {
            throw new Refused(400, "Finnip solo puede tomar en cuenta luces, enchufes, persianas, clima y bocinas");
        }
    }

    async function labels(id: string) {
        try {
            return await registry.getLabels(id);
        } catch (error) {
            if (error instanceof RegistryError && error.code === "not_found") {
                throw new Refused(404, "Ese dispositivo no está en el registro de Home Assistant y no se puede etiquetar");
            }
            throw error;
        }
    }

    async function modes(): Promise<Mode[]> {
        const ids = (await homeAssistant.getStates())
            .map((entity) => entity.entity_id)
            .filter((id) => id.startsWith("script.modo_"));
        const found = await Promise.all(ids.map(async (id) => {
            const slug = id.slice("script.modo_".length);
            const config = SLUG.test(slug) ? await homeAssistant.getScriptConfig(scriptId(slug)) : undefined;
            return config ? readMode(slug, config) : undefined;
        }));
        return found.filter((mode): mode is Mode => mode !== undefined);
    }

    function slugOf(slug: string) {
        if (!SLUG.test(slug)) throw new Refused(400, "Nombre de modo inválido");
        return slug;
    }

    async function mode(slug: string) {
        const config = await homeAssistant.getScriptConfig(scriptId(slugOf(slug)));
        if (!config) throw new Refused(404, "Ese modo no existe");
        return readMode(slug, config);
    }

    return {
        /** Entities Finnip does not see yet, of the domains it may take into account. */
        async candidates() {
            const [labeled, entities] = await Promise.all([
                homeAssistant.labeledEntityIds(DEVICE_LABEL), homeAssistant.getStates(),
            ]);
            const seen = new Set(labeled);
            return entities
                .filter((entity) => !seen.has(entity.entity_id))
                .filter((entity) => EXPOSABLE_DOMAINS.includes(domainOf(entity.entity_id) as (typeof EXPOSABLE_DOMAINS)[number]))
                .map((entity) => ({
                    id: entity.entity_id,
                    name: typeof entity.attributes.friendly_name === "string" ? entity.attributes.friendly_name : entity.entity_id,
                    domain: domainOf(entity.entity_id),
                    state: entity.state,
                }));
        },

        async expose(id: string) {
            exposable(id);
            const current = await labels(id);
            if (!current.includes(DEVICE_LABEL)) await registry.setLabels(id, [...current, DEVICE_LABEL]);
            return (await devices.get(id)) ?? { id };
        },

        /** Drops the label; returns the modes that still use the device, so Finnip can say so. */
        async hide(id: string) {
            exposable(id);
            const current = await labels(id);
            if (current.includes(DEVICE_LABEL)) await registry.setLabels(id, current.filter((label) => label !== DEVICE_LABEL));
            const usedBy = (await modes()).filter((mode) => mode.steps?.some((step) => step.device === id)).map((mode) => mode.name);
            return { id, hidden: true, used_by_modes: usedBy };
        },

        modes,
        mode,

        /** Creates or replaces the mode. Every step is checked like a direct order; one bad step refuses it all. */
        async save(slug: string, body: { name?: string; music: boolean; steps: { device: string; action: string; params: Record<string, unknown> }[] }) {
            const id = scriptId(slugOf(slug));
            const existing = await homeAssistant.getScriptConfig(id);
            if (existing && !readMode(slug, existing).editable) {
                throw new Refused(409, "Ese modo tiene pasos editados a mano en Home Assistant; edítalo ahí");
            }
            const sequence: HaStep[] = [];
            for (const [index, raw] of body.steps.entries()) {
                const device = await devices.get(raw.device);
                const checked = checkStep(raw, device);
                if ("error" in checked) throw new Refused(400, `Paso ${index + 1} (${raw.device}, ${raw.action}): ${checked.error}`);
                sequence.push(toHa(checked.step, device!));
            }
            const name = body.name?.trim() || existing?.alias || `Modo ${slug.replace(/_/g, " ")}`;
            await homeAssistant.saveScriptConfig(id, {
                ...(existing?.icon ? { icon: existing.icon } : {}),
                alias: /^modo\b/i.test(name) ? name : `Modo ${name}`, // "Modo X" is what the voice fast path matches
                description: body.music ? MUSIC_ON : MUSIC_OFF,
                sequence,
            });
            for (let attempt = 1; ; attempt++) {
                try {
                    const current = await registry.getLabels(`script.${id}`);
                    if (!current.includes(DEVICE_LABEL)) await registry.setLabels(`script.${id}`, [...current, DEVICE_LABEL]);
                    break;
                } catch (error) {
                    const pending = error instanceof RegistryError && error.code === "not_found";
                    if (!pending || attempt >= LABEL_TRIES) throw error;
                    await sleep(labelWaitMs);
                }
            }
            return mode(slug);
        },

        async remove(slug: string) {
            const id = scriptId(slugOf(slug));
            if (!(await homeAssistant.getScriptConfig(id))) throw new Refused(404, "Ese modo no existe");
            await homeAssistant.deleteScriptConfig(id);
            return { slug, deleted: true };
        },
    };
}
export type AdminService = ReturnType<typeof createAdminService>;
