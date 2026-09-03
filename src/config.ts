import * as z from "zod";

export const configSchema = z.object({
    TELEGRAM_TOKEN: z.string().min(1, "TELEGRAM_TOKEN is required"),
    WEBHOOK_SECRET: z.string().min(1, "WEBHOOK_SECRET is required"),
    PORT: z.coerce.number().default(8787),
});

export type Config = z.infer<typeof configSchema>;
export const config = configSchema.parse(process.env);