import { config } from '../config.js';
import { UserError } from '../utils/UserError.js';

// Flash es el que trae el tier gratuito sin tarjeta (1500 peticiones al día).
const MODEL = 'gemini-flash-latest';
const API_URL = `https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:generateContent`;

const PROMPT = `Esta es la foto de un ticket de compra o recibo. Descríbelo en UNA sola frase
en español, como si le contaras a alguien qué compraste y cuánto pagaste.

Incluye, solo si aparecen en la imagen:
- El TOTAL pagado. Es el total final, no el subtotal, no el IVA, no el efectivo entregado ni el cambio.
- El nombre del negocio.
- Qué se compró, en general (no la lista completa de productos).
- La forma de pago si viene (efectivo, débito, crédito).
- La fecha si viene y NO es la de hoy.

Ejemplo: "Compra de despensa en Súper Soriana por 484.07 pagada en efectivo el 05/09/2026".

No inventes nada que no esté en la imagen. Si no logras leer el total, responde exactamente: ILEGIBLE`;

/**
 * El tier gratuito se satura por rachas: contesta en 1.4s o truena con 503
 * "high demand" y timeouts. Medido varias veces, no es el modelo leyendo mal,
 * es disponibilidad. Por eso reintenta en vez de rendirse al primer intento.
 */
async function callGemini(body: string): Promise<string | undefined> {
    const delays = [0, 1_000, 3_000];

    for (const [attempt, delay] of delays.entries()) {
        if (delay) {
            await new Promise((resolve) => setTimeout(resolve, delay));
        }

        try {
            const response = await fetch(API_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'x-goog-api-key': config.GEMINI_API_KEY! },
                body,
                signal: AbortSignal.timeout(25_000),
            });

            if (response.ok) {
                const json = await response.json() as {
                    candidates?: { content?: { parts?: { text?: string }[] } }[];
                };

                return json.candidates?.[0]?.content?.parts?.[0]?.text;
            }

            // 429 y 5xx son pasajeros; un 400 o un 403 no se arreglan reintentando.
            if (response.status !== 429 && response.status < 500) {
                throw new Error(`Gemini respondió ${response.status}: ${(await response.text()).slice(0, 200)}`);
            }

            console.warn(`Gemini ${response.status} en el intento ${attempt + 1}`);
        } catch (error) {
            // Solo el timeout se reintenta; cualquier otro error (incluido el 4xx
            // que lanzamos arriba) sube tal cual.
            if (!(error instanceof Error) || error.name !== 'TimeoutError') {
                throw error;
            }

            console.warn(`Gemini timeout en el intento ${attempt + 1}`);
        }
    }

    throw new UserError('Google anda saturado y no pudo leer la foto 😮‍💨 Vuelve a mandarla o escríbeme el gasto.');
}

/**
 * Lee el ticket con un modelo de visión y lo resume en una frase, que luego pasa
 * por classifyMessage como si la hubieras escrito tú.
 *
 * Se resume en vez de devolver el JSON ya clasificado a propósito: las categorías,
 * los métodos de pago y las fechas relativas ya se validan en ai.service contra tu
 * hoja. Duplicar ese prompt aquí sería tener dos verdades que se desincronizan.
 */
export async function describeReceipt(image: Buffer, mimeType: string): Promise<string> {
    if (!config.GEMINI_API_KEY) {
        throw new UserError('Todavía no tengo configurada la lectura de fotos 📷 Escríbeme el gasto.');
    }

    const body = JSON.stringify({
        contents: [{
            parts: [
                { inline_data: { mime_type: mimeType, data: image.toString('base64') } },
                { text: PROMPT },
            ],
        }],
        // Leer un ticket no necesita razonar, y en el tier gratis cada token de
        // más es tiempo de espera.
        generationConfig: { thinkingConfig: { thinkingBudget: 0 } },
    });

    const description = (await callGemini(body))?.trim();

    if (!description || description.includes('ILEGIBLE')) {
        throw new UserError('No pude leer esa foto 🔍 Intenta con más luz, o escríbeme el gasto.');
    }

    return description;
}
