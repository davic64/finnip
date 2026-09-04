import { google } from 'googleapis';
import { config } from '../config.js';
import formatDate from '../utils/formatDate.js'

const credentials = JSON.parse(
    Buffer.from(config.GOOGLE_SERVICE_ACCOUNT_KEY, 'base64').toString('utf-8')
);

const auth = new google.auth.GoogleAuth({
    credentials,
    scopes: ['https://www.googleapis.com/auth/spreadsheets'],
});

const sheets = google.sheets({ version: 'v4', auth });

export async function recordExpense(expense: {
    date: Date;
    category: string;
    amount: number;
    description: string;
    method: string;
    expenseType: string;
}) {
    const appendResult = await sheets.spreadsheets.values.append({
        spreadsheetId: config.SPREADSHEET_ID,
        range: "Gastos!A:A",
        valueInputOption: "USER_ENTERED",
        insertDataOption: "INSERT_ROWS",
        requestBody: {
            values: [[formatDate(expense.date)]]
        }
    });

    const updateRange = appendResult.data.updates?.updatedRange;

    if (!updateRange) {
        throw new Error("Failed to append the date to the spreadsheet.");
    }

    const match = updateRange.match(/\d+/);
    const row = Number(match?.[0]);

    await sheets.spreadsheets.values.update({
        spreadsheetId: config.SPREADSHEET_ID,
        range: `Gastos!C${row}:H${row}`,
        valueInputOption: "USER_ENTERED",
        requestBody: {
            values: [[
                expense.category,
                expense.description,
                expense.amount,
                expense.method,
                expense.expenseType,
                "Registrado por Finnip"
            ]]
        }
    });
}