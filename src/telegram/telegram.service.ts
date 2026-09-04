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

/**
 * Muestra "escribiendo…" mientras pensamos. Telegram lo apaga solo a los ~5s,
 * y no lo repetimos: si algo tarda más que eso, el problema es la tardanza.
 */
export async function sendTyping(chatId: number) {
    await fetch(`${API_URL}/sendChatAction`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chat_id: chatId, action: 'typing' }),
    }).catch((error) => console.error('No se pudo mandar el typing:', error));
}

/** Nota de voz. Best-effort igual que el TTS: si falla, ya mandamos el texto. */
export async function sendVoice(chatId: number, audio: Buffer) {
    const form = new FormData();

    form.append('chat_id', String(chatId));
    form.append('voice', new Blob([new Uint8Array(audio)], { type: 'audio/ogg' }), 'finnip.ogg');

    const response = await fetch(`${API_URL}/sendVoice`, { method: 'POST', body: form });

    if (!response.ok) {
        console.error(`Telegram sendVoice falló: ${response.status} ${await response.text()}`);
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
