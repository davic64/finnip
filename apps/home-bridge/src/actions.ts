import { z } from "zod";
import type { Device } from "./devices.js";
import { colorsMatch } from "./utils/color.js";

export interface ActionDef<I> {
    input: z.ZodType<I>;
    // HA service in the device's own domain, e.g. light.turn_on.
    service: string;
    data?(input: I): Record<string, unknown>;
    // Device-specific limits a static schema cannot express. Returns the error message.
    check?(input: I, device: Device): string | undefined;
    // Whether the state read after the command matches what was asked (before: the state it started from).
    confirm(input: I, actual: Device, before: Device): boolean;
}

const define = <I>(def: ActionDef<I>) => def;
const noInput = z.object({});
const percent = z.number().int().min(1).max(100);
const channel = z.number().int().min(0).max(255);
const words = z.string().trim().min(1).max(200);
// Music service named when asking Alexa to play something (linked in the Alexa app).
const MUSIC_SERVICE = "Apple Music";
// Alexa can shop by voice. A command for her is text the model wrote, so it may carry an injected
// order: refuse anything that looks like buying. (Turning off voice purchasing in the Alexa app is the
// real fix; this is the belt to that braces.)
const PURCHASE = /(?<![\p{L}\p{N}])(compr|cómpr|orden|ordén|pid|píd|pedir|pedido|buy|order|purchas|checkout)/iu;

export const ACTIONS = {
    on: define({ input: noInput, service: "turn_on", confirm: (_, actual) => actual.state === "on" }),
    // script.turn_on starts the script without waiting; it may already be "off" when read back.
    run: define({ input: noInput, service: "turn_on", confirm: () => true }),
    off: define({ input: noInput, service: "turn_off", confirm: (_, actual) => actual.state === "off" }),
    brightness: define({
        input: z.object({ brightness: percent }),
        service: "turn_on",
        data: (input) => ({ brightness_pct: input.brightness }),
        confirm: (input, actual) => actual.state === "on" && actual.brightness === input.brightness,
    }),
    color: define({
        input: z.object({ rgb: z.tuple([channel, channel, channel]), brightness: percent.default(100) }),
        service: "turn_on",
        data: (input) => ({ rgb_color: input.rgb, brightness_pct: input.brightness }),
        confirm: (input, actual) => actual.state === "on" && actual.brightness === input.brightness &&
            colorsMatch(input.rgb, actual.rgb_color ?? null),
    }),
    // White light by temperature ("blanco cálido" ~2700 K), within the light's own range.
    color_temp: define({
        input: z.object({ kelvin: z.number().int().min(1000).max(12000), brightness: percent.optional() }),
        service: "turn_on",
        data: (input) => ({
            color_temp_kelvin: input.kelvin,
            ...(input.brightness === undefined ? {} : { brightness_pct: input.brightness }),
        }),
        check: (input, device) => {
            const { min_color_temp_kelvin: min, max_color_temp_kelvin: max } = device;
            if ((min != null && input.kelvin < min) || (max != null && input.kelvin > max)) {
                return `Color temperature must be between ${min} and ${max} K`;
            }
        },
        confirm: (input, actual) => actual.state === "on" && actual.color_temp_kelvin != null &&
            Math.abs(actual.color_temp_kelvin - input.kelvin) <= 100 &&
            (input.brightness === undefined || actual.brightness === input.brightness),
    }),
    open: define({
        input: noInput, service: "open_cover",
        confirm: (_, actual) => actual.state === "open" || actual.state === "opening",
    }),
    close: define({
        input: noInput, service: "close_cover",
        confirm: (_, actual) => actual.state === "closed" || actual.state === "closing",
    }),
    stop: define({
        input: noInput, service: "stop_cover",
        confirm: (_, actual) => actual.state !== "opening" && actual.state !== "closing",
    }),
    position: define({
        input: z.object({ position: z.number().int().min(0).max(100) }),
        service: "set_cover_position",
        data: (input) => ({ position: input.position }),
        confirm: (input, actual) => actual.current_position === input.position,
    }),
    temperature: define({
        input: z.object({ temperature: z.number() }),
        service: "set_temperature",
        data: (input) => ({ temperature: input.temperature }),
        check: (input, device) => {
            const { min_temp: min, max_temp: max } = device;
            if ((min != null && input.temperature < min) || (max != null && input.temperature > max)) {
                return `Temperature must be between ${min} and ${max}`;
            }
        },
        confirm: (input, actual) => actual.temperature === input.temperature,
    }),
    play: define({
        input: z.object({ query: words }),
        service: "play_media",
        // Spoken to Alexa like the user would say it: the APPLE_MUSIC search type read "song by artist"
        // as a playlist name and failed; Alexa's own language understanding finds songs, artists and playlists.
        data: (input) => ({ media_content_type: "custom", media_content_id: `reproduce ${input.query} en ${MUSIC_SERVICE}` }),
        check: (input) => PURCHASE.test(input.query) ? "Purchases through Alexa are not allowed" : undefined,
        // Already playing: "playing" proves nothing until the song changes (Alexa takes a few seconds).
        confirm: (_, actual, before) => actual.state === "playing" &&
            (before.state !== "playing" || actual.media_title !== before.media_title),
    }),
    command: define({
        input: z.object({ text: words }),
        service: "play_media",
        data: (input) => ({ media_content_type: "custom", media_content_id: input.text }),
        check: (input) => PURCHASE.test(input.text) ? "Purchases through Alexa are not allowed" : undefined,
        confirm: (_, actual) => actual.state !== "unavailable", // Alexa reacts a moment later
    }),
    pause: define({ input: noInput, service: "media_pause", confirm: (_, actual) => actual.state !== "playing" }),
    resume: define({ input: noInput, service: "media_play", confirm: (_, actual) => actual.state === "playing" }),
    volume: define({
        input: z.object({ volume: z.number().int().min(0).max(100) }),
        service: "volume_set",
        data: (input) => ({ volume_level: input.volume / 100 }),
        confirm: (input, actual) => actual.volume === input.volume,
    }),
    // A select's choice, e.g. the LED strip's audio effect ("mic_rhythm").
    option: define({
        input: z.object({ option: z.string().min(1).max(100) }),
        service: "select_option",
        data: (input) => ({ option: input.option }),
        check: (input, device) => device.options?.includes(input.option) ? undefined : "Unsupported option",
        confirm: (input, actual) => actual.state === input.option,
    }),
    // A number setting, e.g. the LED strip's microphone sensitivity.
    value: define({
        input: z.object({ value: z.number() }),
        service: "set_value",
        data: (input) => ({ value: input.value }),
        check: (input, device) => {
            const { min, max } = device;
            if ((min != null && input.value < min) || (max != null && input.value > max)) {
                return `Value must be between ${min} and ${max}`;
            }
        },
        confirm: (input, actual) => Number(actual.state) === input.value,
    }),
    hvac_mode: define({
        input: z.object({ hvac_mode: z.string().min(1) }),
        service: "set_hvac_mode",
        data: (input) => ({ hvac_mode: input.hvac_mode }),
        check: (input, device) =>
            device.hvac_modes?.includes(input.hvac_mode) ? undefined : "Unsupported HVAC mode",
        confirm: (input, actual) => actual.state === input.hvac_mode,
    }),
};

export type ActionName = keyof typeof ACTIONS;

// Object.hasOwn keeps inherited keys such as "toString" or "__proto__" out.
export function findAction(name: string): ActionDef<unknown> | undefined {
    return Object.hasOwn(ACTIONS, name) ? ACTIONS[name as ActionName] as ActionDef<unknown> : undefined;
}
