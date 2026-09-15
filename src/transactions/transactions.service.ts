import { computePace } from '../ai/ai.context.js';
import { persist, state } from '../state/state.service.js';
import type { Transaction } from '../ai/ai.service.js';
import {
    addToGoal,
    deleteRow,
    findGoal,
    getCurrentBalance,
    getExpenses,
    getGoals,
    recordExpense,
    recordIncome,
    type ExpenseRow,
} from '../sheets/sheets.service.js';
import { sendMessage } from '../telegram/telegram.service.js';
import formatDate from '../utils/formatDate.js';
import formatMoney from '../utils/formatMoney.js';
import { UserError } from '../utils/UserError.js';

export const DEFAULT_METHOD = 'Débito';

/**
 * Apartar dinero se registra como GASTO en esta categoría, no como una columna
 * nueva: así sale del "dinero disponible" (que es ingresos - gastos) y además
 * llena la fila "Ahorro y deudas" del 50/30/20 del Tablero.
 * El nombre tiene que existir tal cual en Config!A (hoy es A23).
 */
const SAVINGS_CATEGORY = 'Ahorro e inversión';
const SAVINGS_METHOD = 'Transferencia SPEI';

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

    if (last.goal) {
        // El gasto ya no existe; si esto falla, la meta queda inflada y solo el
        // usuario puede arreglarlo, así que hay que decírselo con la celda exacta.
        await addToGoal(last.goal.row, -last.goal.amount).catch(() => {
            throw new UserError(
                `Borré el gasto, pero no pude restar ${formatMoney(last.goal!.amount)} de Metas!C${last.goal!.row}. Ajústalo a mano 🙏`
            );
        });
    }

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

/**
 * Al registrar un ingreso, recordarle lo que le toca apartar. La hoja calcula la
 * aportación MENSUAL (Metas!F) y él cobra quincenal, así que va la mitad: ese es
 * todo el puente entre "mensual" y "quincenal", sin acumuladores ni cron.
 *
 * Solo entran las metas CON fecha objetivo: sin fecha, Metas!F trae todo lo que
 * falta (no una mensualidad) y el recordatorio sería una cifra absurda.
 */
async function savingsReminder(): Promise<string> {
    const goals = (await getGoals().catch(() => [])).filter(
        (goal) => goal.deadline && goal.monthly > 0
    );

    if (!goals.length) {
        return '';
    }

    return [
        '',
        '',
        '🐷 Esta quincena te toca apartar:',
        ...goals.map((goal) => `• ${goal.name}: ${formatMoney(goal.monthly / 2)}`),
        '',
        'Dime "aparta X para <meta>" cuando lo hagas.',
    ].join('\n');
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

    const [row, reminder] = await Promise.all([
        recordIncome({
            date,
            source: transaction.source,
            incomeType: transaction.incomeType,
            amount: transaction.amount,
        }),
        savingsReminder(),
    ]);

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
        ].filter(Boolean).join('\n') + reminder
    );
}

/**
 * Apartar dinero: un gasto en "Ahorro e inversión" MÁS la suma en Metas!C. Las
 * dos escrituras van en paralelo; si la del gasto falla, la meta queda inflada,
 * pero el error sube y el usuario se entera en el mismo mensaje.
 */
export async function recordSaving(
    chatId: number,
    saving: { amount: number; goalName: string; date?: string }
) {
    const goal = findGoal(await getGoals(), saving.goalName);

    if (!goal) {
        throw new UserError(`No tengo ninguna meta que se llame "${saving.goalName}" 🤔 Créala con /meta.`);
    }

    const date = saving.date ?? formatDate();

    const [row, saved] = await Promise.all([
        recordExpense({
            date,
            category: SAVINGS_CATEGORY,
            amount: saving.amount,
            description: `Aportación a ${goal.name}`,
            method: SAVINGS_METHOD,
            expenseType: 'Fijo',
        }),
        addToGoal(goal.row, saving.amount),
    ]);

    state.lastRecords[chatId] = {
        sheet: 'Gastos',
        row,
        summary: `la aportación de ${formatMoney(saving.amount)} a ${goal.name}`,
        goal: { row: goal.row, amount: saving.amount },
    };
    persist();

    const missing = Math.max(0, goal.target - saved);
    const progress = goal.target > 0 ? ` (${Math.round(Math.min(1, saved / goal.target) * 100)}%)` : '';

    await sendMessage(
        chatId,
        [
            `🐷 Aparté ${formatMoney(saving.amount)} para ${goal.name}`,
            '',
            `📊 Llevas ${formatMoney(saved)} de ${formatMoney(goal.target)}${progress}`,
            missing > 0 ? `🎯 Te faltan ${formatMoney(missing)}` : '🎉 ¡Meta cumplida!',
            dateLine(date),
        ].filter(Boolean).join('\n')
    );
}
