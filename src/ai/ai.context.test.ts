import assert from 'node:assert/strict';
import { test } from 'node:test';
import { buildFinancialContext } from './ai.context.js';

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

test('avisa cuántas filas quedaron fuera del detalle', () => {
    const many = Array.from({ length: 405 }, () => expense('01/09/2026', 'Comida', 1));
    const { omitted, text } = buildFinancialContext(many, [], '25/09/2026', 1000);

    assert.equal(omitted, 5);
    // Los totales sí incluyen las 405, aunque el detalle esté recortado.
    assert.match(text, /2026-09: 405\.00/);
});
