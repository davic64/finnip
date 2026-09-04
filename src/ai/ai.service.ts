import OpenAI from 'openai'
import { config } from '../config.js'
import { getCategories, getExpenseTypes, getIncomeSources, getIncomeTypes } from '../sheets/sheets.service.js';
import * as z from 'zod';

const client = new OpenAI({
    apiKey: config.DEEPSEEK_API_KEY,
    baseURL: 'https://api.deepseek.com',
});

const expenseExtractionSchema = z.object({
    amount: z.number(),
    description: z.string(),
    category: z.string(),
    expenseType: z.string(),
});

const gastoResultSchema = z.object({
    type: z.literal('gasto'),
    amount: z.number(),
    description: z.string(),
    category: z.string(),
    expenseType: z.string(),
});

const ingresoResultSchema = z.object({
    type: z.literal('ingreso'),
    amount: z.number(),
    description: z.string(),
    source: z.string(),
    incomeType: z.string(),
});

const transactionResultSchema = z.discriminatedUnion('type', [gastoResultSchema, ingresoResultSchema]);

export async function extractTransactionFromText(text: string) {
    const [categories, expenseTypes, incomeSources, incomeTypes] = await Promise.all([
        getCategories(),
        getExpenseTypes(),
        getIncomeSources(),
        getIncomeTypes(),
    ]);

    const systemPrompt = `Eres un asistente que clasifica mensajes en español sobre finanzas personales.

Primero decide si el mensaje describe un GASTO (dinero que sale) o un INGRESO (dinero que entra).

Si es un GASTO, responde con este JSON:
{"type": "gasto", "amount": number, "description": string, "category": string, "expenseType": string}
Categorías válidas: ${categories.join(', ')}
Tipos de gasto válidos: ${expenseTypes.join(', ')}
- Fijo: gasto recurrente y predecible, mismo monto aproximado cada mes.
- Variable: gasto necesario pero que cambia de monto cada vez.
- Hormiga: gasto pequeño e impulsivo, no esencial, que suma con el tiempo.

Si es un INGRESO, responde con este JSON:
{"type": "ingreso", "amount": number, "description": string, "source": string, "incomeType": string}
Fuentes válidas: ${incomeSources.join(', ')}
Tipos de ingreso válidos: ${incomeTypes.join(', ')}

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

    const parsed = transactionResultSchema.parse(JSON.parse(raw));

    if (parsed.type === 'gasto') {
        if (!categories.includes(parsed.category)) {
            throw new Error(`Categoría inválida: ${parsed.category}`);
        }
        if (!expenseTypes.includes(parsed.expenseType)) {
            throw new Error(`Tipo de gasto inválido: ${parsed.expenseType}`);
        }
    } else {
        if (!incomeSources.includes(parsed.source)) {
            throw new Error(`Fuente inválida: ${parsed.source}`);
        }
        if (!incomeTypes.includes(parsed.incomeType)) {
            throw new Error(`Tipo de ingreso inválido: ${parsed.incomeType}`);
        }
    }

    return parsed;
}