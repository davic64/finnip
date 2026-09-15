import assert from 'node:assert/strict';
import { test } from 'node:test';
import { buildFinancialContext, computePace, formatGoals } from './ai.context.js';

const expense = (date: string, category: string, amount: number) => ({
    date,
    category,
    description: 'x',
    amount,
    method: 'Débito',
    expenseType: 'Variable',
});

test('suma por mes y por categoría, y separa el mes en curso', () => {
    const { text } = buildFinancialContext(
        [
            expense('01/09/2026', 'Comida', 100),
            expense('15/09/2026', 'Comida', 50.5),
            expense('20/09/2026', 'Transporte', 30),
            expense('10/08/2026', 'Comida', 999),
        ],
        [{ date: '05/09/2026', source: 'Nómina', incomeType: 'Fijo', amount: 5000 }],
        '25/09/2026',
        1000
    );

    assert.match(text, /Mes en curso: 2026-09/);
    assert.match(text, /Gastos totales por mes: 2026-08: 999\.00 \| 2026-09: 180\.50/);
    assert.match(text, /Ingresos totales por mes: 2026-09: 5000\.00/);
    // El gasto de agosto no debe contar en el desglose del mes en curso.
    assert.match(text, /por categoría: Comida: 150\.50 \| Transporte: 30\.00/);
});

test('calcula ritmo, proyección y días hasta la quincena', () => {
    // Día 4 de septiembre (30 días), 400 gastados, saldo 5500.
    const { text } = buildFinancialContext(
        [expense('01/09/2026', 'Comida', 300), expense('03/09/2026', 'Comida', 100)],
        [],
        '04/09/2026',
        5500
    );

    assert.match(text, /Hoy es el día 4 de 30/);
    assert.match(text, /promedio 100\.00 por día/);
    assert.match(text, /a este ritmo: 3000\.00/);
    assert.match(text, /Próxima quincena: día 15, faltan 11 días/);
    assert.match(text, /hasta 500\.00 por día/);
});

test('pasado el 15, la quincena que viene es fin de mes', () => {
    const { text } = buildFinancialContext(
        [expense('20/09/2026', 'Comida', 100)],
        [],
        '25/09/2026',
        1000
    );

    assert.match(text, /Quincena en curso \(días 16-30\): lleva gastado 100\.00/);
    assert.match(text, /Próxima quincena: día 30, faltan 5 días/);
    assert.match(text, /hasta 200\.00 por día/);
});

test('computePace separa lo gastado hoy de lo del mes', () => {
    const pace = computePace(
        [
            expense('01/09/2026', 'Comida', 300),
            expense('04/09/2026', 'Comida', 120),
            expense('04/09/2026', 'Transporte', 80),
        ],
        '04/09/2026',
        5500
    );

    assert.equal(pace.spent, 500);
    assert.equal(pace.todaySpent, 200);
    assert.equal(pace.daysLeft, 11);
    assert.equal(pace.safePerDay, 500);
    assert.equal(pace.nextPayday, 15);
});

test('el día 15 ya cobraste, así que el siguiente pago es fin de mes', () => {
    const pace = computePace([], '15/09/2026', 900);

    assert.equal(pace.nextPayday, 30);
    assert.equal(pace.daysLeft, 15);
    assert.equal(pace.safePerDay, 60);
});

test('el último día del mes no divide entre cero', () => {
    const pace = computePace([], '30/09/2026', 900);

    assert.equal(pace.daysLeft, 0);
    assert.equal(pace.safePerDay, 900);
    assert.ok(Number.isFinite(pace.safePerDay));
});

test('avisa cuántas filas quedaron fuera del detalle', () => {
    const many = Array.from({ length: 405 }, () => expense('01/09/2026', 'Comida', 1));
    const { omitted, text } = buildFinancialContext(many, [], '25/09/2026', 1000);

    assert.equal(omitted, 5);
    // Los totales sí incluyen las 405, aunque el detalle esté recortado.
    assert.match(text, /2026-09: 405\.00/);
});

const goal = (name: string, target: number, saved: number, deadline: string, monthly: number) => ({
    row: 2, name, target, saved, deadline, monthly,
});

test('con fecha objetivo parte la aportación mensual en dos quincenas', () => {
    const text = formatGoals([goal('Vacaciones', 30000, 4500, '01/06/2027', 3000)]);

    assert.match(text, /Vacaciones: lleva 4500\.00 de 30000\.00, faltan 25500\.00/);
    assert.match(text, /3000\.00 al mes = 1500\.00 por quincena/);
});

// Sin fecha, Metas!F trae TODO lo que falta: partirlo en quincenas diría
// "aparta $34,588" y sería basura. Es el único caso que puede mentir feo.
test('sin fecha objetivo no inventa una aportación por quincena', () => {
    const text = formatGoals([goal('Fondo de emergencia', 69177, 0, '', 69177)]);

    const line = text.split('\n').find((row) => row.startsWith('- Fondo'))!;

    assert.match(line, /SIN fecha objetivo/);
    assert.doesNotMatch(line, /por quincena|al mes/);
});

test('sin metas lo dice en vez de quedarse callado', () => {
    assert.match(formatGoals([]), /no tiene ninguna registrada/);
});
