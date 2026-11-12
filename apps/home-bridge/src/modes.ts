import { ACTIONS } from "./actions.js";
import type { Device } from "./devices.js";

// A mode is a Home Assistant script modo_<slug> whose steps are Home Bridge actions on exposed devices.
// Only state actions: no play (Finnip picks the music when the mode runs), no command (free text to
// Alexa), no run (modes do not nest).
export const MODE_ACTIONS = [
    "on", "off", "brightness", "color", "color_temp", "open", "close", "stop", "position",
    "temperature", "hvac_mode", "pause", "resume", "volume", "option", "value",
] as const;
export type ModeAction = (typeof MODE_ACTIONS)[number];
export type Step = { device: string; action: ModeAction; params: Record<string, unknown> };
export type HaStep = Record<string, unknown>;

export const SLUG = /^[a-z0-9_]{1,40}$/;
export const scriptId = (slug: string) => `modo_${slug}`;
// The mode's music, readable in Home Assistant as the script's description: Finnip picks it (true), none
// (false), or this exact query for Alexa ("la playlist 80s Hard Rock", "la estación de Coldplay").
export const MUSIC_ON = "Finnip: con música";
export const MUSIC_OFF = "Finnip: sin música";
const MUSIC_QUERY = "Finnip: música: ";
export type Music = boolean | string;
export function musicOf(description: string | undefined): Music {
    const text = description?.trim() ?? "";
    if (text === MUSIC_OFF) return false;
    return text.startsWith(MUSIC_QUERY) ? text.slice(MUSIC_QUERY.length).trim() || true : true;
}
export const describeMusic = (music: Music) =>
    typeof music === "string" ? MUSIC_QUERY + music : music ? MUSIC_ON : MUSIC_OFF;

const isModeAction = (name: string): name is ModeAction => (MODE_ACTIONS as readonly string[]).includes(name);
const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

/** A validated step as Home Assistant runs it. One unavailable device does not abort the whole mode. */
export function toHa(step: { action: ModeAction; params: Record<string, unknown> }, device: Device): HaStep {
    const def = ACTIONS[step.action];
    const data = (def.data as ((input: unknown) => Record<string, unknown>) | undefined)?.(step.params) ?? {};
    return {
        action: `${device.domain}.${def.service}`,
        target: { entity_id: device.id },
        ...(Object.keys(data).length ? { data } : {}),
        continue_on_error: true,
    };
}

// Home Assistant's data keys back to action inputs; which action it was is decided by re-encoding.
function guessInput(data: Record<string, unknown>): Record<string, unknown> {
    const input: Record<string, unknown> = {};
    if ("brightness_pct" in data) input.brightness = data.brightness_pct;
    if ("rgb_color" in data) input.rgb = data.rgb_color;
    if ("color_temp_kelvin" in data) input.kelvin = data.color_temp_kelvin;
    if (typeof data.volume_level === "number") input.volume = Math.round(data.volume_level * 100);
    for (const key of ["position", "temperature", "hvac_mode", "option", "value"]) if (key in data) input[key] = data[key];
    return input;
}

const STEP_KEYS = new Set(["action", "service", "target", "data", "continue_on_error"]);

/** The Home Bridge step this Home Assistant step is, or undefined if it is anything else (a delay, a
 *  condition, another service, several targets): such a mode was edited by hand and is not editable. */
export function fromHa(step: HaStep): Step | undefined {
    if (Object.keys(step).some((key) => !STEP_KEYS.has(key))) return undefined;
    const [domain, service] = String(step.action ?? step.service ?? "").split(".");
    const entity = (step.target as { entity_id?: unknown } | undefined)?.entity_id;
    if (!domain || !service || typeof entity !== "string" || !entity.startsWith(`${domain}.`)) return undefined;
    const data = (step.data ?? {}) as Record<string, unknown>;
    for (const name of MODE_ACTIONS) {
        const def = ACTIONS[name];
        if (def.service !== service) continue;
        const parsed = def.input.safeParse(guessInput(data));
        if (!parsed.success) continue;
        const params = parsed.data as Record<string, unknown>;
        const encoded = toHa({ action: name, params }, { id: entity, domain } as Device);
        if (same(encoded.data ?? {}, data)) return { device: entity, action: name, params };
    }
    return undefined;
}

export type Mode = { slug: string; name: string; music: Music; editable: boolean; steps: Step[] | null };

export function readMode(slug: string, config: { alias?: string; description?: string; sequence: HaStep[] }): Mode {
    const steps = config.sequence.map(fromHa);
    const editable = steps.every((step) => step !== undefined);
    return {
        slug,
        name: config.alias ?? `Modo ${slug.replace(/_/g, " ")}`,
        music: musicOf(config.description),
        editable,
        steps: editable ? (steps as Step[]) : null,
    };
}

/** Problem with a step against the exposed device it targets, or undefined when it is valid. */
export function checkStep(step: { action: string; params: Record<string, unknown> }, device: Device | undefined):
    { error: string } | { step: { action: ModeAction; params: Record<string, unknown> } } {
    if (!device) return { error: "dispositivo no expuesto a Finnip" };
    if (!isModeAction(step.action)) return { error: `la acción ${step.action} no se permite en un modo` };
    if (!device.capabilities.includes(step.action)) return { error: `${device.name} no soporta ${step.action}` };
    const def = ACTIONS[step.action];
    const parsed = def.input.safeParse(step.params);
    if (!parsed.success) return { error: "valores inválidos" };
    const problem = (def.check as ((input: unknown, device: Device) => string | undefined) | undefined)?.(parsed.data, device);
    if (problem) return { error: problem };
    return { step: { action: step.action, params: parsed.data as Record<string, unknown> } };
}
