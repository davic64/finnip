import { google } from 'googleapis';
import * as z from 'zod';
import { config } from '../config.js';
import { auth } from '../google/google.auth.js';
import formatDate from '../utils/formatDate.js';
import { UserError } from '../utils/UserError.js';

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

// Los catálogos de Config casi nunca cambian y se leían en CADA mensaje: eran
// ~600ms fijos por gasto. Con el TTL, editar la hoja tarda hasta 1h en verse;
// /recargar lo fuerza sin esperar.
const CATALOG_TTL_MS = 60 * 60 * 1000;
const catalogCache = new Map<string, { values: string[]; readAt: number }>();

async function readCatalog(range: string): Promise<string[]> {
    const cached = catalogCache.get(range);

    if (cached && Date.now() - cached.readAt < CATALOG_TTL_MS) {
        return cached.values;
    }

    const response = await sheets.spreadsheets.values.get({
        spreadsheetId: config.SPREADSHEET_ID,
        range,
    });

    const values = (response.data.values ?? []).map((row) => row[0]).filter(Boolean);

    catalogCache.set(range, { values, readAt: Date.now() });

    return values;
}

export const clearCatalogCache = () => catalogCache.clear();

// La hoja escribe los meses como "sep2026". Intl no sirve aquí: en es-MX
// septiembre abrevia "sept" y no casaría con la hoja.
const MONTH_KEYS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

function currentMonthKey(): string {
    const [, month, year] = formatDate().split('/');

    return `${MONTH_KEYS[Number(month) - 1]}${year}`;
}

/**
 * Acumulado al cierre del mes en curso, del histórico mensual (Tablero!I6:M18).
 * Se busca la fila por nombre de mes calculado en JS: NO se lee Tablero!B10 ni
 * ninguna celda del resumen, porque todas dependen del selector manual de B4.
 */
export async function getCurrentBalance(): Promise<number> {
    const response = await sheets.spreadsheets.values.get({
        spreadsheetId: config.SPREADSHEET_ID,
        range: 'Tablero!I6:M18',
        valueRenderOption: 'UNFORMATTED_VALUE',
        dateTimeRenderOption: 'FORMATTED_STRING',
    });

    const month = currentMonthKey();
    const row = (response.data.values ?? []).find(
        (cells) => String(cells[0]).trim().toLowerCase() === month
    );

    if (!row) {
        throw new UserError(
            `No encontré ${month} en el histórico del Tablero 🤔 Revisa que "Mes analizado" (Tablero!B2) esté en el mes actual.`
        );
    }

    const balance = z.coerce.number().safeParse(row[4]);

    if (!balance.success) {
        throw new UserError(`El acumulado al cierre de ${month} no es un número en tu hoja.`);
    }

    return balance.data;
}

/**
 * Salud financiera y promedios de 12 meses (columnas F-G del Tablero), en texto
 * plano para el prompt. Las etiquetas salen de la hoja, así que si las renombras
 * esto sigue funcionando.
 *
 * A propósito NO incluye "Resumen del mes" (A6:B14): esos números son del periodo
 * elegido a mano en B4, no del mes, y meterlos sería mentirle a la IA.
 */
export async function getFinancialHealthData(): Promise<string> {
    const response = await sheets.spreadsheets.values.get({
        spreadsheetId: config.SPREADSHEET_ID,
        range: 'Tablero!A5:M18',
        valueRenderOption: 'UNFORMATTED_VALUE',
        dateTimeRenderOption: 'FORMATTED_STRING',
    });

    const rows = response.data.values ?? [];
    // El rango arranca en la fila 5, así que la fila N de la hoja es rows[N - 5].
    const at = (sheetRow: number) => rows[sheetRow - 5] ?? [];
    const pairs = (from: number, to: number) => {
        const lines: string[] = [];

        for (let sheetRow = from; sheetRow <= to; sheetRow++) {
            const [label, value] = [at(sheetRow)[5], at(sheetRow)[6]];

            if (label && value !== undefined && value !== '') {
                lines.push(`- ${label}: ${value}`);
            }
        }

        return lines.join('\n') || '- sin datos';
    };

    return [
        'SALUD FINANCIERA (Tablero de la hoja):',
        pairs(6, 11),
        '',
        'PROMEDIOS DE LOS ÚLTIMOS 12 MESES CON DATOS:',
        pairs(13, 15),
    ].join('\n');
}

export const getCategories = () => readCatalog('Config!A3:A40');
export const getPaymentMethods = () => readCatalog('Config!D3:D20');
export const getExpenseTypes = () => readCatalog('Config!F3:F20');
export const getIncomeSources = () => readCatalog('Config!H3:H20');
export const getIncomeTypes = () => readCatalog('Config!L3:L20');

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