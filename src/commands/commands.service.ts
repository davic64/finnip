import * as z from 'zod';
import {
    clearCatalogCache,
    getCategories,
    getExpenseTypes,
    getIncomeSources,
    getIncomeTypes,
    getPaymentMethods,
} from '../sheets/sheets.service.js';
import { sendMessage } from '../telegram/telegram.service.js';
import { recordAndConfirm } from '../transactions/transactions.service.js';

type Answers = Record<string, string>;

type Step = {
    key: string;
    question: string;
    options?: () => Promise<string[]>;
};

type Flow = {
    steps: Step[];
    finish: (chatId: number, answers: Answers) => Promise<void>;
};

const AMOUNT_STEP: Step = { key: 'amount', question: '¿De cuánto? Solo el número, ej. 250.50' };
const DESCRIPTION_STEP: Step = { key: 'description', question: '¿En qué fue? Descríbelo corto.' };

const flows: Record<string, Flow> = {
    gasto: {
        steps: [
            AMOUNT_STEP,
            DESCRIPTION_STEP,
            { key: 'category', question: '¿Qué categoría?', options: getCategories },
            { key: 'expenseType', question: '¿Qué tipo de gasto?', options: getExpenseTypes },
            { key: 'method', question: '¿Cómo lo pagaste?', options: getPaymentMethods },
        ],
        finish: (chatId, answers) =>
            recordAndConfirm(chatId, {
                type: 'gasto',
                amount: Number(answers.amount),
                description: answers.description,
                category: answers.category,
                expenseType: answers.expenseType,
                method: answers.method,
            }),
    },
    ingreso: {
        steps: [
            AMOUNT_STEP,
            DESCRIPTION_STEP,
            { key: 'source', question: '¿De qué fuente viene?', options: getIncomeSources },
            { key: 'incomeType', question: '¿Qué tipo de ingreso?', options: getIncomeTypes },
        ],
        finish: (chatId, answers) =>
            recordAndConfirm(chatId, {
                type: 'ingreso',
                amount: Number(answers.amount),
                description: answers.description,
                source: answers.source,
                incomeType: answers.incomeType,
            }),
    },
};

// ponytail: sesiones en memoria. Bot de un solo usuario; si se reinicia el proceso
// se pierde la conversación a medias y basta con volver a mandar /gasto.
const SESSION_TTL_MS = 15 * 60 * 1000;
const sessions = new Map<number, { flow: string; index: number; answers: Answers; updatedAt: number }>();

const amountSchema = z.coerce.number().positive();

const HELP = `Soy Finnip 🐷

• Mándame un mensaje suelto: "gasté 250 en el súper" o "me pagaron 5000 de nómina".
• Mándame la foto de un ticket y lo leo.
• Pregúntame lo que sea: "¿cuánto llevo gastado este mes?".
• /consejo y te mando un consejo en audio con tus números.
• /gasto o /ingreso para registrarlo paso a paso.
• /cancelar para salirte de un registro a medias.
• /recargar si editaste los catálogos de la hoja.`;

/**
 * Atiende comandos y respuestas de un registro guiado.
 * Regresa false si el mensaje no le toca (para que siga el camino de IA).
 */
export async function handleCommandFlow(chatId: number, text: string): Promise<boolean> {
    if (text.startsWith('/')) {
        const [rawCommand, ...args] = text.trim().split(/\s+/);
        const command = rawCommand.slice(1).split('@')[0].toLowerCase();

        if (command === 'recargar') {
            clearCatalogCache();
            await sendMessage(chatId, '🔄 Listo, releo los catálogos de tu hoja.');
            return true;
        }

        if (command === 'cancelar') {
            const had = sessions.delete(chatId);
            await sendMessage(chatId, had ? '👌 Listo, lo cancelé.' : 'No tenías nada a medias.');
            return true;
        }

        const flow = flows[command];

        if (!flow) {
            await sendMessage(chatId, HELP);
            return true;
        }

        // Lo que venga después del comando pre-llena monto y descripción: /gasto 250 café
        const answers: Answers = {};
        const amount = amountSchema.safeParse(args[0]);

        if (amount.success) {
            answers.amount = String(amount.data);

            if (args.length > 1) {
                answers.description = args.slice(1).join(' ');
            }
        }

        const index = flow.steps.findIndex((step) => !(step.key in answers));

        sessions.set(chatId, { flow: command, index, answers, updatedAt: Date.now() });
        await askOrFinish(chatId);
        return true;
    }

    const session = sessions.get(chatId);

    if (!session) {
        return false;
    }

    if (Date.now() - session.updatedAt > SESSION_TTL_MS) {
        sessions.delete(chatId);
        await sendMessage(chatId, '⌛ Pasó mucho rato, cancelé ese registro. Mándame /gasto o /ingreso otra vez.');
        return true;
    }

    const step = flows[session.flow].steps[session.index];
    const answer = text.trim();

    if (step.options) {
        const options = await step.options();

        if (!options.includes(answer)) {
            await sendMessage(chatId, `Esa no está en la lista 🙈 ${step.question}`, options);
            return true;
        }
    } else if (step.key === 'amount') {
        const amount = amountSchema.safeParse(answer.replace(/[$,\s]/g, ''));

        if (!amount.success) {
            await sendMessage(chatId, 'Necesito un número mayor a 0, ej. 250.50');
            return true;
        }

        session.answers[step.key] = String(amount.data);
        session.index += 1;
        session.updatedAt = Date.now();
        await askOrFinish(chatId);
        return true;
    } else if (!answer) {
        await sendMessage(chatId, step.question);
        return true;
    }

    session.answers[step.key] = answer;
    session.index += 1;
    session.updatedAt = Date.now();
    await askOrFinish(chatId);
    return true;
}

async function askOrFinish(chatId: number) {
    const session = sessions.get(chatId);

    if (!session) {
        return;
    }

    const flow = flows[session.flow];
    const step = flow.steps[session.index];

    if (!step) {
        sessions.delete(chatId);
        await flow.finish(chatId, session.answers);
        return;
    }

    await sendMessage(chatId, step.question, await step.options?.());
}
