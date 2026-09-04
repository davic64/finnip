import * as z from 'zod';
import { answerFinancialQuestion, classifyMessage } from '../ai/ai.service.js';
import { handleCommandFlow } from '../commands/commands.service.js';
import { extractTextFromImage } from '../drive/drive.service.js';
import { downloadFile, sendMessage, sendTyping } from '../telegram/telegram.service.js';
import { recordAndConfirm } from '../transactions/transactions.service.js';
import { config } from '../config.js';
import { toUserMessage } from '../utils/UserError.js';

const messageSchema = z.object({
    message: z.object({
        chat: z.object({ id: z.number() }),
        text: z.string().min(1).optional(),
        // Telegram manda varios tamaños de la misma foto, de menor a mayor.
        photo: z.array(z.object({ file_id: z.string() })).min(1).optional(),
    }),
});

export const handleTelegramUpdate = async (update: unknown) => {
    const parsed = messageSchema.safeParse(update);

    // ponytail: ignora lo que no sea texto ni foto (stickers, edits, etc.).
    if (!parsed.success) {
        return;
    }

    const { chat, text, photo } = parsed.data.message;

    // El secret_token protege el endpoint, pero el bot sigue siendo público en
    // Telegram: sin esto, cualquiera escribiría en la hoja.
    if (!config.ALLOWED_CHAT_IDS.includes(chat.id)) {
        console.warn(`Chat no autorizado: ${chat.id}`);
        return;
    }

    try {
        if (text && await handleCommandFlow(chat.id, text)) {
            return;
        }

        await sendTyping(chat.id);

        let content = text;

        if (!content && photo) {
            const largest = photo[photo.length - 1];
            const image = await downloadFile(largest.file_id);
            content = await extractTextFromImage(image, 'image/jpeg');
        }

        if (!content) {
            return;
        }

        const result = await classifyMessage(content);

        if (result.type === 'pregunta') {
            await sendMessage(chat.id, await answerFinancialQuestion(content));
            return;
        }

        await recordAndConfirm(chat.id, result);
    } catch (error) {
        console.error('Error procesando mensaje:', error);

        await sendMessage(chat.id, toUserMessage(error));
    }
};
