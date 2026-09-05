import { mkdirSync } from 'node:fs';
import { dirname } from 'node:path';
import { createWorker, type Worker } from 'tesseract.js';
import { config } from '../config.js';
import { UserError } from '../utils/UserError.js';

// Junto al estado, para no tirar el spa.traineddata (3.2MB) en la raíz. Si montas
// el volumen de Dokploy ahí, se descarga una sola vez en la vida del servidor.
const CACHE_PATH = dirname(config.STATE_FILE);

/**
 * OCR local con Tesseract. Nada sale del servidor: ni Google, ni cuotas, ni llaves.
 *
 * El worker se crea una sola vez y se reutiliza: arrancarlo descarga y carga el
 * modelo de español (3.2MB) y tarda ~2s, así que hacerlo por foto sería absurdo.
 */
let workerPromise: Promise<Worker> | null = null;

function getWorker(): Promise<Worker> {
    // Si el directorio no existe, tesseract.js no cachea y vuelve a bajar el
    // modelo en CADA arranque. Medido: 528ms en frío contra 107ms con caché.
    mkdirSync(CACHE_PATH, { recursive: true });

    workerPromise ??= createWorker('spa', undefined, { cachePath: CACHE_PATH });

    return workerPromise;
}

/** Precarga el modelo al arrancar, para que la primera foto no pague el arranque. */
export async function warmUpOcr() {
    try {
        await getWorker();
        console.log('OCR listo');
    } catch (error) {
        console.error('No se pudo iniciar el OCR:', error);
        workerPromise = null;
    }
}

export async function readReceipt(image: Buffer): Promise<string> {
    const worker = await getWorker();
    const { data } = await worker.recognize(image);
    const text = data.text.trim();

    if (!text) {
        throw new UserError('No pude leer esa foto 🔍 Intenta con más luz y que el ticket salga derecho.');
    }

    return text;
}
