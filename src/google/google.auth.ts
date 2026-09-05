import { google } from 'googleapis';
import { config } from '../config.js';

const credentials = JSON.parse(
    Buffer.from(config.GOOGLE_SERVICE_ACCOUNT_KEY, 'base64').toString('utf-8')
);

export const auth = new google.auth.GoogleAuth({
    credentials,
    // Solo Sheets. Los tickets los lee Gemini con su propia API key, así que esta
    // Service Account no necesita permisos sobre nada más.
    scopes: ['https://www.googleapis.com/auth/spreadsheets'],
});
