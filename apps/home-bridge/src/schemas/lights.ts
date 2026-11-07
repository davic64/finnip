import { z } from "zod";

export const lightSchema = z.object({
    entity_id: z.literal("light.leds_monitores"),
    state: z.string(),
    attributes: z.object({
        brightness: z.number().nullable().optional(),
        rgb_color: z.array(z.number()).nullable().optional(),
    }).loose(),
});

export const colorSchema = z.object({
    rgb: z.tuple([
        z.number().int().min(0).max(255),
        z.number().int().min(0).max(255),
        z.number().int().min(0).max(255),
    ]),
    brightness: z.number().int().min(1).max(100).default(100),
});
export type ColorInput = z.infer<typeof colorSchema>;
