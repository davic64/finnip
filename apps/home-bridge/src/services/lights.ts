import { colorsMatch } from "../utils/color.js";
import type { ColorInput } from "../schemas/lights.js";
import type { HomeAssistantService } from "./home-assistant.js";

export function createLightsService(homeAssistant: HomeAssistantService) {
    return {
        getState: homeAssistant.getLightState,
        async setColor(input: ColorInput) {
            await homeAssistant.callService("turn_on", {
                rgb_color: input.rgb,
                brightness_pct: input.brightness,
            });
            const actual = await homeAssistant.getLightState();
            return {
                success: true,
                confirmed: actual.state === "on" && actual.brightness === input.brightness &&
                    colorsMatch(input.rgb, actual.rgb_color),
                requested: input,
                actual,
            };
        },
        turnOn: () => switchPower("on"),
        turnOff: () => switchPower("off"),
    };

    // Read back after the command so callers see what HA reports, not just what was sent.
    async function switchPower(power: "on" | "off") {
        await homeAssistant.callService(`turn_${power}`);
        const actual = await homeAssistant.getLightState();
        return {
            success: true,
            action: `turn_${power}`,
            device: "Leds Monitores",
            confirmed: actual.state === power,
            actual,
        };
    }
}
export type LightsService = ReturnType<typeof createLightsService>;
