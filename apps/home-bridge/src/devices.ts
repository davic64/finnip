import type { ActionName } from "./actions.js";

// Home Assistant label that opts an entity into Finnip. Untagged entities stay invisible.
export const DEVICE_LABEL = "finnip";

// Domains Finnip may control. A labeled entity outside this list (lock, alarm…) is ignored.
// script: the "modos" (Modo estudio, Modo cine…), edited in Home Assistant and only run from here.
export const ALLOWED_DOMAINS = ["light", "switch", "cover", "climate", "media_player", "script"] as const;
export type Domain = (typeof ALLOWED_DOMAINS)[number];

export interface Entity {
    entity_id: string;
    state: string;
    attributes: Record<string, unknown>;
}

export interface Device {
    id: string;
    name: string;
    domain: Domain;
    state: string;
    capabilities: ActionName[];
    brightness?: number | null;
    color_mode?: string | null;
    rgb_color?: number[] | null;
    color_temp_kelvin?: number | null;
    min_color_temp_kelvin?: number | null;
    max_color_temp_kelvin?: number | null;
    current_position?: number | null;
    current_temperature?: number | null;
    temperature?: number | null;
    min_temp?: number | null;
    max_temp?: number | null;
    hvac_modes?: string[];
    volume?: number | null;
    media_title?: string | null;
    media_artist?: string | null;
    media_album?: string | null;
    media_image?: string | null;
    media_duration?: number | null;
    media_position?: number | null;
    media_position_at?: string | null;
    /** Modes (scripts): whether Finnip picks music when it runs (from the script's description). */
    music?: boolean;
}

const ENTITY_ID = /^([a-z_]+)\.[a-z0-9_]+$/;

// Also guards URL building: only well-formed ids of allowed domains get through.
export function domainOf(entityId: string): Domain | undefined {
    const domain = ENTITY_ID.exec(entityId)?.[1];
    return ALLOWED_DOMAINS.find((allowed) => allowed === domain);
}

const text = (value: unknown) => typeof value === "string" && value ? value : null;
const num = (value: unknown) => typeof value === "number" && Number.isFinite(value) ? value : null;
const strings = (value: unknown) =>
    Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
const numbers = (value: unknown) =>
    Array.isArray(value) && value.every((item) => typeof item === "number") ? value as number[] : null;

// Color modes that accept rgb_color; HA converts between them.
const COLOR_MODES = new Set(["hs", "rgb", "rgbw", "rgbww", "xy"]);
// Bits from HA's CoverEntityFeature and ClimateEntityFeature.
const COVER_FEATURES = [[1, "open"], [2, "close"], [4, "position"], [8, "stop"]] as const;
const CLIMATE_TARGET_TEMPERATURE = 1;

function capabilitiesOf(domain: Domain, attributes: Record<string, unknown>): ActionName[] {
    const features = num(attributes.supported_features) ?? 0;
    switch (domain) {
        case "switch":
            return ["on", "off"];
        case "script":
            return ["run"];
        case "light": {
            const modes = strings(attributes.supported_color_modes);
            const capabilities: ActionName[] = ["on", "off"];
            if (modes.some((mode) => mode !== "onoff")) capabilities.push("brightness");
            if (modes.some((mode) => COLOR_MODES.has(mode))) capabilities.push("color");
            if (modes.includes("color_temp")) capabilities.push("color_temp");
            return capabilities;
        }
        case "cover":
            return COVER_FEATURES.filter(([bit]) => features & bit).map(([, name]) => name);
        case "media_player":
            // Alexa speakers (Alexa Media Player integration).
            return ["play", "command", "pause", "resume", "volume"];
        case "climate": {
            const capabilities: ActionName[] = [];
            if (features & CLIMATE_TARGET_TEMPERATURE) capabilities.push("temperature");
            if (strings(attributes.hvac_modes).length > 0) capabilities.push("hvac_mode");
            return capabilities;
        }
    }
}

export function toDevice(entity: Entity, domain: Domain): Device {
    const attributes = entity.attributes;
    const base: Device = {
        id: entity.entity_id,
        name: typeof attributes.friendly_name === "string" ? attributes.friendly_name : entity.entity_id,
        domain,
        state: entity.state,
        capabilities: capabilitiesOf(domain, attributes),
    };
    switch (domain) {
        case "switch":
        case "script":
            return base;
        case "light": {
            const rawBrightness = num(attributes.brightness);
            const colorMode = typeof attributes.color_mode === "string" ? attributes.color_mode : null;
            return {
                ...base,
                brightness: rawBrightness === null ? null : Math.round(rawBrightness / 255 * 100),
                color_mode: colorMode,
                // In color_temp mode HA also reports an approximate rgb_color; replaying it as rgb lights
                // the color LEDs (orange) instead of the white ones, so only the kelvin is offered.
                rgb_color: colorMode === "color_temp" ? null : numbers(attributes.rgb_color),
                color_temp_kelvin: num(attributes.color_temp_kelvin),
                min_color_temp_kelvin: num(attributes.min_color_temp_kelvin),
                max_color_temp_kelvin: num(attributes.max_color_temp_kelvin),
            };
        }
        case "cover":
            return { ...base, current_position: num(attributes.current_position) };
        case "media_player": {
            const level = num(attributes.volume_level);
            return {
                ...base,
                volume: level === null ? null : Math.round(level * 100),
                media_title: text(attributes.media_title),
                media_artist: text(attributes.media_artist),
                media_album: text(attributes.media_album_name),
                // Cover art: only an https URL (Alexa gives Apple's CDN), never a relative HA path.
                media_image: text(attributes.entity_picture)?.startsWith("https://") ? attributes.entity_picture as string : null,
                media_duration: num(attributes.media_duration),
                media_position: num(attributes.media_position),
                media_position_at: text(attributes.media_position_updated_at),
            };
        }
        case "climate":
            return {
                ...base,
                current_temperature: num(attributes.current_temperature),
                temperature: num(attributes.temperature),
                min_temp: num(attributes.min_temp),
                max_temp: num(attributes.max_temp),
                hvac_modes: strings(attributes.hvac_modes),
            };
    }
}
