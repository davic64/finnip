export type DeviceType = "light" | "switch";

export interface Device {
    entityId: string;
    type: DeviceType;
    name: string;
}

export type DeviceCatalog = Record<string, Device>;

// Add new devices here. The key is the id used in the URL: /devices/<key>.
// `type` must match the entity_id domain (light.*, switch.*).
export const DEVICES = {
    monitorLeds: { entityId: "light.leds_monitores", type: "light", name: "Leds Monitores" },
} as const satisfies DeviceCatalog;

// Object.hasOwn keeps inherited keys such as "toString" or "__proto__" out.
export function findDevice(catalog: DeviceCatalog, id: string): Device | undefined {
    return Object.hasOwn(catalog, id) ? catalog[id] : undefined;
}
