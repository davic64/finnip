import { z } from "zod";

export const envSchema = z.object({
    HA_URL: z.url(),
    HA_TOKEN: z.string().min(1),
    BRIDGE_API_KEY: z.string().min(32),
});
export type BridgeEnv = z.infer<typeof envSchema>;
