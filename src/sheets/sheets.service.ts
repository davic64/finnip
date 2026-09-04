import { google } from 'googleapis';
import * as z from 'zod';
import { config } from '../config.js';
import { auth } from '../google/google.auth.js';

const sheets = google.sheets({ version: 'v4', auth });

const dateSchema = z.string().regex(/^\d{2}\/\d{2}\/\d{4}$/);

const expenseRowSchema = z.object({
    date: dateSchema,
    category: z.string().min(1),
    description: z.string(),
    amount: z.coerce.number(),
    method: z.string(),
    expenseType: z.string(),
});

const incomeRowSchema = z.object({
    date: dateSchema,
    source: z.string().min(1),
    incomeType: z.string(),
    amount: z.coerce.number(),
});

export type ExpenseRow = z.infer<typeof expenseRowSchema>;
export type IncomeRow = z.infer<typeof incomeRowSchema>;

/**
 * Lee un rango y descarta las filas que no cuadran con el schema.
 * Eso tira encabezados, filas vacías y basura a media hoja sin lógica extra.
 */
async function readRows<T>(range: string, toRow: (cells: any[]) => unknown, schema: z.ZodType<T>): Promise<T[]> {
    const response = await sheets.spreadsheets.values.get({
        spreadsheetId: config.SPREADSHEET_ID,
        range,
        valueRenderOption: 'UNFORMATTED_VALUE',
        dateTimeRenderOption: 'FORMATTED_STRING',
    });

    return (response.data.values ?? [])
        .map((cells) => schema.safeParse(toRow(cells)))
        .filter((result) => result.success)
        .map((result) => result.data);
}

export function getExpenses(): Promise<ExpenseRow[]> {
    return readRows(
        'Gastos!A:H',
        (cells) => ({
            date: cells[0],
            category: cells[2],
            description: cells[3] ?? '',
            amount: cells[4],
            method: cells[5] ?? '',
            expenseType: cells[6] ?? '',
        }),
        expenseRowSchema
    );
}

export function getIncomes(): Promise<IncomeRow[]> {
    return readRows(
        'Ingresos!A:F',
        (cells) => ({
            date: cells[0],
            source: cells[2],
            incomeType: cells[3] ?? '',
            amount: cells[4],
        }),
        incomeRowSchema
    );
}

export async function getCategories(): Promise<string[]> {
    const response = await sheets.spreadsheets.values.get({
        spreadsheetId: config.SPREADSHEET_ID,
        range: 'Config!A3:A40',
    });

    const rows = response.data.values ?? [];

    return rows.map((row) => row[0]);
}

export async function getPaymentMethods(): Promise<string[]> {
    const response = await sheets.spreadsheets.values.get({
        spreadsheetId: config.SPREADSHEET_ID,
        range: 'Config!D3:D20',
    });

    const rows = response.data.values ?? [];

    return rows.map((row) => row[0]);
}

export async function getExpenseTypes(): Promise<string[]> {
    const response = await sheets.spreadsheets.values.get({
        spreadsheetId: config.SPREADSHEET_ID,
        range: 'Config!F3:F20',
    });

    const rows = response.data.values ?? [];

    return rows.map((row) => row[0]);
}

export async function getIncomeTypes(): Promise<string[]> {
    const response = await sheets.spreadsheets.values.get({
        spreadsheetId: config.SPREADSHEET_ID,
        range: 'Config!L3:L20',
    });

    const rows = response.data.values ?? [];

    return rows.map((row) => row[0]);
}

export async function getIncomeSources(): Promise<string[]> {
    const response = await sheets.spreadsheets.values.get({
        spreadsheetId: config.SPREADSHEET_ID,
        range: 'Config!H3:H20',
    });

    const rows = response.data.values ?? [];

    return rows.map((row) => row[0]);
}

export async function recordIncome(income: {
    /** dd/MM/yyyy, ya resuelto en la zona del usuario. */
    date: string;
    source: string;
    incomeType: string;
    amount: number;
}) {
    const appendResult = await sheets.spreadsheets.values.append({
        spreadsheetId: config.SPREADSHEET_ID,
        range: "Ingresos!A:A",
        valueInputOption: "USER_ENTERED",
        insertDataOption: "INSERT_ROWS",
        requestBody: {
            values: [[income.date]]
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
        range: `Ingresos!C${row}:F${row}`,
        valueInputOption: "USER_ENTERED",
        requestBody: {
            values: [[
                income.source,
                income.incomeType,
                income.amount,
                "Registrado por Finnip"
            ]]
        }
    });
}

export async function recordExpense(expense: {
    /** dd/MM/yyyy, ya resuelto en la zona del usuario. */
    date: string;
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
            values: [[expense.date]]
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