import * as z from 'zod';
import { config } from '../config.js';

const API_URL = `https://api.telegram.org/bot${config.TELEGRAM_TOKEN}`;
const FILE_URL = `https://api.telegram.org/file/bot${config.TELEGRAM_TOKEN}`;

const getFileResponseSchema = z.object({
    ok: z.literal(true),
    result: z.object({ file_path: z.string().min(1) }),
});

export async function sendMessage(chatId: number, text: string, options?: string[]) {
    const response = await fetch(`${API_URL}/sendMessage`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            chat_id: chatId,
            text,
            reply_markup: options
                ? {
                    keyboard: options.map((option) => [{ text: option }]),
                    resize_keyboard: true,
                    one_time_keyboard: true,
                }
                : { remove_keyboard: true },
        }),
    });

    if (!response.ok) {
        throw new Error(`Telegram sendMessage falló: ${response.status} ${await response.text()}`);
    }
}

export async function downloadFile(fileId: string): Promise<Buffer> {
    const infoResponse = await fetch(`${API_URL}/getFile?file_id=${encodeURIComponent(fileId)}`);

    if (!infoResponse.ok) {
        throw new Error(`Telegram getFile falló: ${infoResponse.status} ${await infoResponse.text()}`);
    }

    const { result } = getFileResponseSchema.parse(await infoResponse.json());
    const fileResponse = await fetch(`${FILE_URL}/${result.file_path}`);

    if (!fileResponse.ok) {
        throw new Error(`No se pudo descargar el archivo de Telegram: ${fileResponse.status}`);
    }

    return Buffer.from(await fileResponse.arrayBuffer());
}
