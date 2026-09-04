import type { Transaction } from '../ai/ai.service.js';
import { recordExpense, recordIncome } from '../sheets/sheets.service.js';
import { sendMessage } from '../telegram/telegram.service.js';
import formatDate from '../utils/formatDate.js';
import formatMoney from '../utils/formatMoney.js';

export const DEFAULT_METHOD = 'Débito';

/** Solo se muestra la fecha cuando NO es hoy, para no ensuciar la confirmación normal. */
const dateLine = (date: string) => (date === formatDate() ? '' : `📅 ${date}`);

/** Escribe la transacción en Sheets y le confirma al usuario. */
export async function recordAndConfirm(chatId: number, transaction: Transaction) {
    // Sin fecha explícita en el mensaje, va la de hoy en la zona del usuario.
    const date = transaction.date ?? formatDate();

    if (transaction.type === 'gasto') {
        const method = transaction.method ?? DEFAULT_METHOD;

        await recordExpense({
            date,
            category: transaction.category,
            amount: transaction.amount,
            description: transaction.description,
            method,
            expenseType: transaction.expenseType,
        });

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
            ].filter(Boolean).join('\n')
        );

        return;
    }

    await recordIncome({
        date,
        source: transaction.source,
        incomeType: transaction.incomeType,
        amount: transaction.amount,
    });

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
