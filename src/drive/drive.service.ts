import { google } from 'googleapis';
import { Readable } from 'node:stream';
import { auth } from '../google/google.auth.js';
import { UserError } from '../utils/UserError.js';

const drive = google.drive({ version: 'v3', auth });

/**
 * Sube la imagen convirtiéndola a Google Doc (eso dispara el OCR de Drive),
 * exporta el texto plano y borra el archivo temporal.
 */
export async function extractTextFromImage(image: Buffer, mimeType: string): Promise<string> {
    const created = await drive.files.create({
        requestBody: {
            name: `finnip-ocr-${crypto.randomUUID()}`,
            mimeType: 'application/vnd.google-apps.document',
        },
        media: {
            mimeType,
            body: Readable.from(image),
        },
        ocrLanguage: 'es',
        fields: 'id',
    });

    const fileId = created.data.id;

    if (!fileId) {
        throw new Error('Drive no regresó el id del archivo con OCR');
    }

    try {
        const exported = await drive.files.export({
            fileId,
            mimeType: 'text/plain',
        });

        const text = String(exported.data ?? '').trim();

        if (!text) {
            throw new UserError('No le entendí nada a esa foto 🔍 Intenta con más luz o escríbeme el gasto.');
        }

        return text;
    } finally {
        await drive.files.delete({ fileId }).catch((error) => {
            console.error('No se pudo borrar el archivo temporal de Drive:', error);
        });
    }
}
