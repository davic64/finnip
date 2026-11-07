import { colorsMatch } from "../utils/color.js";
import type { Device } from "../devices.js";
import type { ColorInput } from "../schemas/devices.js";
import type { HomeAssistantService } from "./home-assistant.js";

export function createDevicesService(homeAssistant: HomeAssistantService) {
    // Read back after the command so callers see what HA reports, not just what was sent.
    async function switchPower(device: Device, power: "on" | "off") {
        await homeAssistant.callService(device, `turn_${power}`);
        const actual = await homeAssistant.getState(device);
        return {
            success: true,
            action: `turn_${power}`,
            device: device.name,
            confirmed: actual.state === power,
            actual,
        };
    }

    return {
        getState: homeAssistant.getState,
        async setColor(device: Device, input: ColorInput) {
            await homeAssistant.callService(device, "turn_on", {
                rgb_color: input.rgb,
                brightness_pct: input.brightness,
            });
            const actual = await homeAssistant.getState(device);
            return {
                success: true,
                confirmed: actual.state === "on" && actual.brightness === input.brightness &&
                    colorsMatch(input.rgb, actual.rgb_color ?? null),
                requested: input,
                actual,
            };
        },
        turnOn: (device: Device) => switchPower(device, "on"),
        turnOff: (device: Device) => switchPower(device, "off"),
    };
}
export type DevicesService = ReturnType<typeof createDevicesService>;
