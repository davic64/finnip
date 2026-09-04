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
 * Arma el contexto que se le pasa al modelo. Los totales se calculan aquí, en código,
 * no los saca el modelo: sumar cientos de filas es justo lo que un LLM hace mal.
 */
export function buildFinancialContext(expenses: ExpenseRow[], incomes: IncomeRow[], today: string) {
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
