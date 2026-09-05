import * as z from "zod";

export const configSchema = z.object({
    TELEGRAM_TOKEN: z.string().min(1, "TELEGRAM_TOKEN is required"),
    WEBHOOK_SECRET: z.string().min(1, "WEBHOOK_SECRET is required"),
    PORT: z.coerce.number().default(8787),
    GOOGLE_SERVICE_ACCOUNT_KEY: z.string().min(1, "GOOGLE_SERVICE_ACCOUNT_KEY is required"),
    SPREADSHEET_ID: z.string().min(1, "SPREADSHEET_ID is required"),
    DEEPSEEK_API_KEY: z.string().min(1, "DEEPSEEK_API_KEY is required"),
    TIMEZONE: z.string().min(1).default("America/Mexico_City"),
    // Monta un volumen de Dokploy sobre esta ruta para que aguante los redeploys.
    STATE_FILE: z.string().min(1).default("./data/state.json"),
    // Opcionales: sin llave, los consejos llegan solo en texto y el bot sigue vivo.
    FISH_AUDIO_API_KEY: z.string().min(1).optional(),
    FISH_VOICE_ID: z.string().min(1).optional(),
    // Lista de chat ids separados por coma. Sin esto cualquiera que encuentre
    // el bot podría escribir en la hoja.
    ALLOWED_CHAT_IDS: z
        .string()
        .min(1, "ALLOWED_CHAT_IDS is required")
        .transform((value) => value.split(",").map((id) => Number(id.trim())))
        .pipe(z.array(z.int()).min(1)),
});

export type Config = z.infer<typeof configSchema>;
export const config = configSchema.parse(process.env);