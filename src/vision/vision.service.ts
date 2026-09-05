import { google } from 'googleapis';
import { auth } from '../google/google.auth.js';
import { UserError } from '../utils/UserError.js';

const vision = google.vision({ version: 'v1', auth });

/**
 * OCR con Cloud Vision. Antes esto pasaba por Drive (subir imagen -> convertir a
 * Doc -> exportar texto -> borrar), pero las Service Accounts ya no tienen cuota
 * de almacenamiento y Drive respondía "storage quota has been exceeded".
 * Vision no guarda nada: manda la imagen, regresa el texto.
 */
export async function extractTextFromImage(image: Buffer): Promise<string> {
    const response = await vision.images.annotate({
        requestBody: {
            requests: [{
                image: { content: image.toString('base64') },
                // DOCUMENT_TEXT_DETECTION lee mejor bloques densos, como un ticket.
                features: [{ type: 'DOCUMENT_TEXT_DETECTION' }],
                imageContext: { languageHints: ['es'] },
            }],
        },
    });

    const result = response.data.responses?.[0];

    if (result?.error?.message) {
        throw new Error(`Cloud Vision: ${result.error.message}`);
    }

    const text = result?.fullTextAnnotation?.text?.trim();

    if (!text) {
        throw new UserError('No le entendí nada a esa foto 🔍 Intenta con más luz o escríbeme el gasto.');
    }

    return text;
}
