import * as z from "zod";

export const configSchema = z.object({
    TELEGRAM_TOKEN: z.string().min(1, "TELEGRAM_TOKEN is required"),
    WEBHOOK_SECRET: z.string().min(1, "WEBHOOK_SECRET is required"),
    PORT: z.coerce.number().default(8787),
    GOOGLE_SERVICE_ACCOUNT_KEY: z.string().min(1, "GOOGLE_SERVICE_ACCOUNT_KEY is required"),
    SPREADSHEET_ID: z.string().min(1, "SPREADSHEET_ID is required"),
    DEEPSEEK_API_KEY: z.string().min(1, "DEEPSEEK_API_KEY is required"),
});

export type Config = z.infer<typeof configSchema>;
export const config = configSchema.parse(process.env);