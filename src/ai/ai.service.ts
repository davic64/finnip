import OpenAI from 'openai'
import { config } from '../config.js'
import { getCategories, getExpenseTypes, getIncomeSources, getIncomeTypes, getPaymentMethods } from '../sheets/sheets.service.js';
import formatDate from '../utils/formatDate.js';
import { UserError } from '../utils/UserError.js';
import * as z from 'zod';

const client = new OpenAI({
    apiKey: config.DEEPSEEK_API_KEY,
    baseURL: 'https://api.deepseek.com',
    // DeepSeek se pone lento por rachas; sin esto un cuelgue deja al usuario
    // esperando para siempre y sin error.
    timeout: 30_000,
    maxRetries: 1,
});

/** dd/MM/yyyy; solo viene cuando el mensaje menciona una fecha distinta a hoy. */
const dateSchema = z.string().regex(/^\d{2}\/\d{2}\/\d{4}$/).optional();

const gastoResultSchema = z.object({
    type: z.literal('gasto'),
    amount: z.number(),
    description: z.string(),
    category: z.string(),
    expenseType: z.string(),
    method: z.string().optional(),
    date: dateSchema,
});

const ingresoResultSchema = z.object({
    type: z.literal('ingreso'),
    amount: z.number(),
    description: z.string(),
    source: z.string(),
    incomeType: z.string(),
    date: dateSchema,
});

const preguntaResultSchema = z.object({
    type: z.literal('pregunta'),
});

const transactionResultSchema = z.discriminatedUnion('type', [gastoResultSchema, ingresoResultSchema]);
const messageResultSchema = z.discriminatedUnion('type', [
    gastoResultSchema,
    ingresoResultSchema,
    preguntaResultSchema,
]);

export type Transaction = z.infer<typeof transactionResultSchema>;
export type MessageResult = z.infer<typeof messageResultSchema>;

/** La IA a veces inventa valores fuera del catálogo de la hoja. */
function check(valid: string[], value: string, label: string) {
    if (!valid.includes(value)) {
        throw new UserError(
            `No supe en qué ${label} ponerlo 🤔 Me salió "${value}", que no está en tu hoja.\n\nOpciones: ${valid.join(', ')}`
        );
    }
}

export async function classifyMessage(text: string): Promise<MessageResult> {
    const [categories, expenseTypes, incomeSources, incomeTypes, paymentMethods] = await Promise.all([
        getCategories(),
        getExpenseTypes(),
        getIncomeSources(),
        getIncomeTypes(),
        getPaymentMethods(),
    ]);

    const systemPrompt = `Eres un asistente que clasifica mensajes en español sobre finanzas personales.
Hoy es ${formatDate()} (formato dd/MM/yyyy).

Primero decide si el mensaje describe un GASTO (dinero que sale), un INGRESO (dinero que entra)
o si es una PREGUNTA sobre las finanzas del usuario (cuánto lleva gastado, en qué gasta más,
cuánto le queda, comparaciones entre meses, etc.).

Si es una PREGUNTA, responde solo con:
{"type": "pregunta"}

Si es un GASTO, responde con este JSON:
{"type": "gasto", "amount": number, "description": string, "category": string, "expenseType": string, "method": string, "date": string}
Categorías válidas: ${categories.join(', ')}
Tipos de gasto válidos: ${expenseTypes.join(', ')}
- Fijo: gasto recurrente y predecible, mismo monto aproximado cada mes.
- Variable: gasto necesario pero que cambia de monto cada vez.
- Hormiga: gasto pequeño e impulsivo, no esencial, que suma con el tiempo.
Métodos de pago válidos: ${paymentMethods.join(', ')}
- "method" solo si el mensaje dice cómo se pagó (efectivo, tarjeta, transferencia...). Si no lo dice, omítelo.

Si es un INGRESO, responde con este JSON:
{"type": "ingreso", "amount": number, "description": string, "source": string, "incomeType": string, "date": string}
Fuentes válidas: ${incomeSources.join(', ')}
Tipos de ingreso válidos: ${incomeTypes.join(', ')}

Sobre "date": solo inclúyelo si el mensaje menciona una fecha distinta de hoy ("ayer", "el lunes",
"el 3 de marzo", "antier"). Resuélvela contra la fecha de hoy y devuélvela en dd/MM/yyyy.
Si el mensaje no menciona fecha, omite el campo.

Responde SOLO con el JSON correspondiente, nada más.`;

    const response = await client.chat.completions.create({
        model: 'deepseek-v4-flash',
        response_format: { type: 'json_object' },
        messages: [
            { role: 'system', content: systemPrompt },
            { role: 'user', content: text },
        ],
    });

    const raw = response.choices[0].message.content;

    if (!raw) {
        throw new Error('DeepSeek no regresó contenido');
    }

    const parsed = messageResultSchema.parse(JSON.parse(raw));

    if (parsed.type === 'pregunta') {
        return parsed;
    }

    if (parsed.type === 'gasto') {
        check(categories, parsed.category, 'categoría');
        check(expenseTypes, parsed.expenseType, 'tipo de gasto');

        if (parsed.method) {
            check(paymentMethods, parsed.method, 'método de pago');
        }
    } else {
        check(incomeSources, parsed.source, 'fuente de ingreso');
        check(incomeTypes, parsed.incomeType, 'tipo de ingreso');
    }

    return parsed;
}

/**
 * Respuesta conversacional libre: sin JSON ni schema. El contexto lo arma quien
 * llama, esta función solo habla con el modelo.
 */
export async function answerFinancialQuestion(question: string, context: string): Promise<string> {
    const systemPrompt = `Eres Finnip, el asistente de finanzas personales del usuario. Hoy es ${formatDate()}.
Todos los montos están en pesos mexicanos (MXN).

Responde SOLO con los datos que vienen abajo. Nunca inventes cifras ni supongas gastos que no aparecen.
Si los datos no alcanzan para responder, dilo claro y di qué falta; jamás rellenes con estimaciones.
Responde en español, corto (máximo 4 líneas), amigable y con los montos formateados como $1,234.56.
Texto plano: nada de markdown, negritas ni asteriscos, que Telegram los muestra tal cual.

DATOS REALES DEL USUARIO:
${context}`;

    const response = await client.chat.completions.create({
        model: 'deepseek-v4-flash',
        messages: [
            { role: 'system', content: systemPrompt },
            { role: 'user', content: question },
        ],
    });

    const answer = response.choices[0].message.content?.trim();

    if (!answer) {
        throw new Error('DeepSeek no regresó respuesta a la pregunta');
    }

    return answer;
}
