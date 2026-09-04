import { config } from '../config.js';

const TTS_URL = 'https://api.fish.audio/v1/tts';
// Modelo gratuito de fish.audio. Si dejan de ofrecerlo, la API responde error y
// caemos a texto solo: hay que cambiar esto por un modelo de paga.
const MODEL = 's2.1-pro-free';

/**
 * Convierte texto a voz. Es best-effort a propósito: si fish.audio falla, tarda
 * o no hay llave configurada, regresa null y el usuario igual recibe su texto.
 */
export async function synthesize(text: string): Promise<Buffer | null> {
    if (!config.FISH_AUDIO_API_KEY) {
        return null;
    }

    try {
        const response = await fetch(TTS_URL, {
            method: 'POST',
            headers: {
                Authorization: `Bearer ${config.FISH_AUDIO_API_KEY}`,
                'Content-Type': 'application/json',
                model: MODEL,
            },
            body: JSON.stringify({
                text,
                // Telegram pide OGG/Opus para las notas de voz.
                format: 'opus',
                ...(config.FISH_VOICE_ID ? { reference_id: config.FISH_VOICE_ID } : {}),
            }),
            signal: AbortSignal.timeout(20_000),
        });

        if (!response.ok) {
            console.error(`fish.audio respondió ${response.status}: ${await response.text()}`);
            return null;
        }

        return Buffer.from(await response.arrayBuffer());
    } catch (error) {
        console.error('No se pudo generar el audio:', error);
        return null;
    }
}
