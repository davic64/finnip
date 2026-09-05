import { google } from 'googleapis';
import { config } from '../config.js';

const credentials = JSON.parse(
    Buffer.from(config.GOOGLE_SERVICE_ACCOUNT_KEY, 'base64').toString('utf-8')
);

export const auth = new google.auth.GoogleAuth({
    credentials,
    scopes: [
        'https://www.googleapis.com/auth/spreadsheets',
        // Cloud Vision (OCR de tickets). Drive ya no se usa: las Service Accounts
        // no tienen cuota de almacenamiento y no podían ni crear el archivo.
        'https://www.googleapis.com/auth/cloud-platform',
    ],
});
