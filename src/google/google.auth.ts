import { google } from 'googleapis';
import { config } from '../config.js';

const credentials = JSON.parse(
    Buffer.from(config.GOOGLE_SERVICE_ACCOUNT_KEY, 'base64').toString('utf-8')
);

export const auth = new google.auth.GoogleAuth({
    credentials,
    scopes: [
        'https://www.googleapis.com/auth/spreadsheets',
        // drive.file basta: solo tocamos archivos que este bot crea.
        'https://www.googleapis.com/auth/drive.file',
    ],
});
