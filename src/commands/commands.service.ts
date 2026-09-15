import * as z from 'zod';
import {
    clearCatalogCache,
    createGoal,
    getCategories,
    getExpenseTypes,
    getGoals,
    getIncomeSources,
    getIncomeTypes,
    getPaymentMethods,
} from '../sheets/sheets.service.js';
import { sendMessage } from '../telegram/telegram.service.js';
import { recordAndConfirm, recordSaving, undoLast } from '../transactions/transactions.service.js';
import formatMoney from '../utils/formatMoney.js';

type Answers = Record<string, string>;

type Step = {
    key: string;
    question: string;
    options?: () => Promise<string[]>;
    /** Qué decir cuando `options()` viene vacío: el paso no se puede contestar. */
    empty?: string;
    /** Regresa el valor ya normalizado, o null para volver a preguntar. */
    validate?: (value: string) => string | null;
    /** Lo que se manda cuando `validate` dice que no. */
    hint?: string;
};

type Flow = {
    steps: Step[];
    finish: (chatId: number, answers: Answers) => Promise<void>;
};

const amountSchema = z.coerce.number().positive();
const DATE_PATTERN = /^\d{2}\/\d{2}\/\d{4}$/;

const parseAmount = (value: string) => {
    const amount = amountSchema.safeParse(value.replace(/[$,\s]/g, ''));

    return amount.success ? String(amount.data) : null;
};

const AMOUNT_STEP: Step = {
    key: 'amount',
    question: '¿De cuánto? Solo el número, ej. 250.50',
    validate: parseAmount,
    hint: 'Necesito un número mayor a 0, ej. 250.50',
};
const DESCRIPTION_STEP: Step = { key: 'description', question: '¿En qué fue? Descríbelo corto.' };
const GOAL_STEP: Step = {
    key: 'goal',
    question: '¿Para qué meta?',
    options: async () => (await getGoals()).map((goal) => goal.name),
    empty: 'Todavía no tienes metas 🐷 Créala con /meta y luego apartamos.',
};

const flows: Record<string, Flow> = {
    apartar: {
        steps: [AMOUNT_STEP, GOAL_STEP],
        finish: (chatId, answers) =>
            recordSaving(chatId, { amount: Number(answers.amount), goalName: answers.goal }),
    },
    meta: {
        steps: [
            { key: 'name', question: '¿Cómo se llama la meta? Ej. Vacaciones' },
            {
                key: 'target',
                question: '¿Cuánto quieres juntar? Solo el número.',
                validate: parseAmount,
                hint: 'Necesito un número mayor a 0, ej. 30000',
            },
            {
                key: 'deadline',
                // Sin fecha la hoja no calcula aportación mensual y el bot no te
                // puede decir cuánto apartar por quincena. Por eso se insiste.
                question: '¿Para cuándo? En dd/MM/yyyy, ej. 01/06/2027.\nEscribe "sin fecha" si aún no sabes (pero entonces no calculo cuánto apartar por quincena).',
                validate: (value) => {
                    const answer = value.trim();

                    if (/^(sin fecha|ninguna|no|-)$/i.test(answer)) {
                        return '';
                    }

                    return DATE_PATTERN.test(answer) ? answer : null;
                },
                hint: 'Así no la leo 🙈 Mándamela como dd/MM/yyyy, ej. 01/06/2027, o escribe "sin fecha".',
            },
        ],
        finish: async (chatId, answers) => {
            const goal = await createGoal({
                name: answers.name,
                target: Number(answers.target),
                deadline: answers.deadline,
            });

            await sendMessage(
                chatId,
                [
                    `🎯 Meta creada: ${goal.name}`,
                    '',
                    `Objetivo: ${formatMoney(goal.target)}`,
                    goal.deadline
                        ? `Fecha: ${goal.deadline} — en cuanto la hoja recalcule te digo cuánto va por quincena al registrar tu ingreso.`
                        : 'Sin fecha objetivo: apartas lo que puedas con /apartar. Ponle fecha en Metas!D cuando la sepas.',
                ].join('\n')
            );
        },
    },
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

const HELP = `Soy Finnip 🐷

• Mándame un mensaje suelto: "gasté 250 en el súper" o "me pagaron 5000 de nómina".
• Mándame la foto de un ticket y lo leo.
• Pregúntame lo que sea: "¿cuánto llevo gastado este mes?".
• /consejo y te mando un consejo en audio con tus números.
• /gasto o /ingreso para registrarlo paso a paso.
• /meta para crear una meta de ahorro.
• /apartar 1500 para mandar dinero de tu disponible a una meta.
• /deshacer borra el último movimiento que registré.
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

        if (command === 'deshacer') {
            await sendMessage(chatId, await undoLast(chatId));
            return true;
        }

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

    let value = answer;

    if (step.options) {
        const options = await step.options();

        if (!options.includes(value)) {
            await sendMessage(chatId, `Esa no está en la lista 🙈 ${step.question}`, options);
            return true;
        }
    } else if (step.validate) {
        const normalized = step.validate(value);

        if (normalized === null) {
            await sendMessage(chatId, step.hint ?? step.question);
            return true;
        }

        value = normalized;
    } else if (!value) {
        await sendMessage(chatId, step.question);
        return true;
    }

    session.answers[step.key] = value;
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

    const options = await step.options?.();

    // Sin opciones el usuario quedaría atrapado: nada de lo que escriba pasa.
    if (options?.length === 0) {
        sessions.delete(chatId);
        await sendMessage(chatId, step.empty ?? 'Esa lista está vacía en tu hoja 🤷');
        return;
    }

    await sendMessage(chatId, step.question, options);
}
