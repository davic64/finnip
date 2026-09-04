import type { ExpenseRow, IncomeRow } from '../sheets/sheets.service.js';

// ponytail: tope de filas de detalle que le mandamos al modelo. Los totales
// siempre salen de TODAS las filas, esto solo recorta el desglose línea por línea.
const MAX_DETAIL_ROWS = 400;

const monthOf = (date: string) => `${date.slice(6)}-${date.slice(3, 5)}`;

function totalsBy<T>(rows: T[], key: (row: T) => string, amount: (row: T) => number) {
    const totals = new Map<string, number>();

    for (const row of rows) {
        totals.set(key(row), (totals.get(key(row)) ?? 0) + amount(row));
    }

    return [...totals].sort(([a], [b]) => a.localeCompare(b));
}

const asLines = (totals: [string, number][]) =>
    totals.map(([key, total]) => `${key}: ${total.toFixed(2)}`).join(' | ') || 'sin datos';

/**
 * Ritmo de gasto y días que faltan para la próxima quincena. Todo esto se calcula
 * aquí porque son justo las cuentas que el modelo hace mal: restar fechas y dividir
 * para proyectar. Sin esto no puede contestar "¿cuánto puedo gastar hasta el 15?".
 *
 * ponytail: quincenas fijas los días 15 y último del mes, como el propio Tablero.
 * Si algún día cobras en otras fechas, esto se vuelve config.
 */
function buildPace(monthExpenses: ExpenseRow[], today: string, balance: number) {
    const day = Number(today.slice(0, 2));
    const month = Number(today.slice(3, 5));
    const year = Number(today.slice(6));
    const daysInMonth = new Date(year, month, 0).getDate();

    const spent = monthExpenses.reduce((total, expense) => total + expense.amount, 0);
    const perDay = spent / day;

    const nextPayday = day < 15 ? 15 : daysInMonth;
    const daysLeft = nextPayday - day;
    // El día de la quincena ya cobras, así que el saldo tiene que estirarse los días previos.
    const safePerDay = daysLeft > 0 ? balance / daysLeft : balance;

    const fortnight = day <= 15 ? 'días 1-15' : `días 16-${daysInMonth}`;
    const fortnightSpent = monthExpenses
        .filter((expense) => (Number(expense.date.slice(0, 2)) <= 15) === (day <= 15))
        .reduce((total, expense) => total + expense.amount, 0);

    return [
        'RITMO Y PLANEACIÓN:',
        `- Hoy es el día ${day} de ${daysInMonth} del mes`,
        `- Dinero disponible ahora: ${balance.toFixed(2)}`,
        `- Gastado en lo que va del mes: ${spent.toFixed(2)} (promedio ${perDay.toFixed(2)} por día)`,
        `- Proyección de gasto a fin de mes a este ritmo: ${(perDay * daysInMonth).toFixed(2)}`,
        `- Quincena en curso (${fortnight}): lleva gastado ${fortnightSpent.toFixed(2)}`,
        `- Próxima quincena: día ${nextPayday}, faltan ${daysLeft} días`,
        `- Puede gastar hasta ${safePerDay.toFixed(2)} por día sin quedarse sin saldo antes de cobrar`,
    ].join('\n');
}

/**
 * Arma el contexto que se le pasa al modelo. Los totales se calculan aquí, en código,
 * no los saca el modelo: sumar cientos de filas es justo lo que un LLM hace mal.
 */
export function buildFinancialContext(
    expenses: ExpenseRow[],
    incomes: IncomeRow[],
    today: string,
    balance: number
) {
    const currentMonth = monthOf(today);
    const monthExpenses = expenses.filter((expense) => monthOf(expense.date) === currentMonth);
    const monthIncomes = incomes.filter((income) => monthOf(income.date) === currentMonth);

    const detail = expenses.slice(-MAX_DETAIL_ROWS);
    const omitted = expenses.length - detail.length;

    return {
        omitted,
        text: [
            `Mes en curso: ${currentMonth}`,
            '',
            buildPace(monthExpenses, today, balance),
            '',
            `Gastos totales por mes: ${asLines(totalsBy(expenses, (e) => monthOf(e.date), (e) => e.amount))}`,
            `Ingresos totales por mes: ${asLines(totalsBy(incomes, (i) => monthOf(i.date), (i) => i.amount))}`,
            '',
            `Gastos del mes en curso por categoría: ${asLines(totalsBy(monthExpenses, (e) => e.category, (e) => e.amount))}`,
            `Gastos del mes en curso por tipo: ${asLines(totalsBy(monthExpenses, (e) => e.expenseType, (e) => e.amount))}`,
            `Ingresos del mes en curso por fuente: ${asLines(totalsBy(monthIncomes, (i) => i.source, (i) => i.amount))}`,
            '',
            omitted > 0
                ? `Últimos ${detail.length} gastos (se omitieron ${omitted} más viejos; los totales de arriba sí los incluyen):`
                : 'Detalle de gastos (fecha | categoría | descripción | monto | método | tipo):',
            ...detail.map((e) =>
                `${e.date} | ${e.category} | ${e.description} | ${e.amount.toFixed(2)} | ${e.method} | ${e.expenseType}`
            ),
        ].join('\n'),
    };
}
