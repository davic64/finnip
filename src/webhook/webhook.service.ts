import * as z from 'zod';
import { answerFinancialQuestion, classifyMessage } from '../ai/ai.service.js';
import { buildFinancialContext } from '../ai/ai.context.js';
import {
    getCurrentBalance,
    getExpenses,
    getFinancialHealthData,
    getIncomes,
} from '../sheets/sheets.service.js';
import formatDate from '../utils/formatDate.js';
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

// Heurística deliberadamente estrecha: un falso positivo contesta en vez de
// registrar (se pierde el gasto), un falso negativo solo cuesta una llamada de más.
const QUESTION_STARTERS = /^(cuánto|cuanto|cuál|cual|cómo voy|como voy|qué tal voy|que tal voy|en qué gasto|en que gasto|me alcanza)\b/i;
// Pedir consejo no lleva signos de interrogación: "dame un consejo", "aconséjame".
const ADVICE_HINTS = /\b(consejo|conséjame|aconséjame|aconsejame|recomienda|recomiendas|recomendación|recomendacion|presupuesto|presupuestar|cómo voy|como voy)\b/i;

// "gasté 500 del presupuesto de comida" es un registro, no una consulta: si el
// mensaje arranca con un verbo de movimiento, gana el registro.
// Ojo: nada de \b al final, que en JS es ASCII y no reconoce frontera tras "gasté".
const TRANSACTION_VERBS = /^(gast[eé]|pagu[eé]|compr[eé]|cobr[eé]|recib[ií]|me pagaron|me depositaron)(\s|$)/i;

const looksLikeQuestion = (text: string) => {
    const trimmed = text.trim();

    if (TRANSACTION_VERBS.test(trimmed)) {
        return false;
    }

    return trimmed.includes('?') || trimmed.includes('¿') || QUESTION_STARTERS.test(trimmed) || ADVICE_HINTS.test(trimmed);
};

/**
 * Junta el contexto real: el saldo del Tablero, la salud financiera de la hoja
 * y el detalle de los movimientos registrados.
 */
async function answerQuestion(question: string): Promise<string> {
    const [balance, health, expenses, incomes] = await Promise.all([
        getCurrentBalance(),
        getFinancialHealthData(),
        getExpenses(),
        getIncomes(),
    ]);

    const detail = buildFinancialContext(expenses, incomes, formatDate(), balance);

    if (detail.omitted > 0) {
        console.log(`Contexto recortado: ${detail.omitted} gastos viejos fuera del detalle`);
    }

    const context = [health, '', detail.text].join('\n');

    return answerFinancialQuestion(question, context);
}

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

        // Preguntar primero "¿esto es pregunta o registro?" cuesta una llamada
        // entera a DeepSeek (1-4s). Si el texto ya se ve como pregunta, nos la
        // saltamos y vamos directo a responder.
        if (looksLikeQuestion(content)) {
            await sendMessage(chat.id, await answerQuestion(content));
            return;
        }

        const result = await classifyMessage(content);

        if (result.type === 'pregunta') {
            await sendMessage(chat.id, await answerQuestion(content));
            return;
        }

        await recordAndConfirm(chat.id, result);
    } catch (error) {
        console.error('Error procesando mensaje:', error);

        await sendMessage(chat.id, toUserMessage(error));
    }
};
