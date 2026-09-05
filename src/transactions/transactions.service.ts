import { computePace } from '../ai/ai.context.js';
import { persist, state } from '../state/state.service.js';
import type { Transaction } from '../ai/ai.service.js';
import {
    deleteRow,
    getCurrentBalance,
    getExpenses,
    recordExpense,
    recordIncome,
    type ExpenseRow,
} from '../sheets/sheets.service.js';
import { sendMessage } from '../telegram/telegram.service.js';
import formatDate from '../utils/formatDate.js';
import formatMoney from '../utils/formatMoney.js';

export const DEFAULT_METHOD = 'Débito';

/**
 * Borra el último movimiento registrado por este chat. La referencia vive en el
 * estado persistido, así que /deshacer sobrevive a un reinicio del proceso. La referencia se limpia
 * ANTES de borrar: si la API falla, prefiero que el usuario reintente a mano a
 * que un segundo /deshacer se lleve una fila que ya no es la suya.
 */
export async function undoLast(chatId: number): Promise<string> {
    const last = state.lastRecords[chatId];

    if (!last) {
        return 'No tengo nada reciente que borrar 🤷 Solo puedo deshacer lo último que registré.';
    }

    delete state.lastRecords[chatId];
    persist();
    await deleteRow(last.sheet, last.row);

    return `🗑️ Borré ${last.summary}`;
}

/**
 * Aviso de ritmo: solo aparece cuando el día ya se pasó del tope, para que no se
 * vuelva ruido que se ignora. Los datos se leen en paralelo con la escritura, así
 * que no le cuesta tiempo a la confirmación.
 */
async function paceWarning(amount: number, expenses: ExpenseRow[], balance: number): Promise<string> {
    const today = formatDate();
    const currentMonth = today.slice(3);
    const pace = computePace(
        expenses.filter((expense) => expense.date.slice(3) === currentMonth),
        today,
        balance
    );

    // Lo recién registrado no viene en la lectura: se hizo en paralelo.
    const todaySpent = pace.todaySpent + amount;

    if (todaySpent <= pace.safePerDay || pace.daysLeft <= 0) {
        return '';
    }

    return `\n\n⚠️ Llevas ${formatMoney(todaySpent)} hoy y tu tope es ${formatMoney(pace.safePerDay)} por día para llegar al ${pace.nextPayday}.`;
}

/** Solo se muestra la fecha cuando NO es hoy, para no ensuciar la confirmación normal. */
const dateLine = (date: string) => (date === formatDate() ? '' : `📅 ${date}`);

/** Escribe la transacción en Sheets y le confirma al usuario. */
export async function recordAndConfirm(chatId: number, transaction: Transaction) {
    // Sin fecha explícita en el mensaje, va la de hoy en la zona del usuario.
    const date = transaction.date ?? formatDate();

    if (transaction.type === 'gasto') {
        const method = transaction.method ?? DEFAULT_METHOD;

        // Las lecturas del aviso van en paralelo con la escritura: si fallan, el
        // gasto igual queda registrado y solo nos quedamos sin advertencia.
        const [row, expenses, balance] = await Promise.all([
            recordExpense({
                date,
                category: transaction.category,
                amount: transaction.amount,
                description: transaction.description,
                method,
                expenseType: transaction.expenseType,
            }),
            getExpenses().catch(() => null),
            getCurrentBalance().catch(() => null),
        ]);

        state.lastRecords[chatId] = {
            sheet: 'Gastos',
            row,
            summary: `el gasto de ${formatMoney(transaction.amount)}${transaction.description ? ` en ${transaction.description}` : ''}`,
        };
        persist();

        const warning = expenses && balance !== null
            ? await paceWarning(transaction.amount, expenses, balance)
            : '';

        await sendMessage(
            chatId,
            [
                '✅ Gasto registrado',
                '',
                `💸 ${formatMoney(transaction.amount)}`,
                transaction.description && `📝 ${transaction.description}`,
                `🏷️ ${transaction.category} · ${transaction.expenseType}`,
                `💳 ${method}`,
                dateLine(date),
            ].filter(Boolean).join('\n') + warning
        );

        return;
    }

    const row = await recordIncome({
        date,
        source: transaction.source,
        incomeType: transaction.incomeType,
        amount: transaction.amount,
    });

    state.lastRecords[chatId] = {
        sheet: 'Ingresos',
        row,
        summary: `el ingreso de ${formatMoney(transaction.amount)}`,
    };
    persist();

    await sendMessage(
        chatId,
        [
            '✅ Ingreso registrado',
            '',
            `💰 ${formatMoney(transaction.amount)}`,
            transaction.description && `📝 ${transaction.description}`,
            `🏷️ ${transaction.source} · ${transaction.incomeType}`,
            dateLine(date),
        ].filter(Boolean).join('\n')
    );
}
