const formatter = new Intl.NumberFormat('es-MX', {
    style: 'currency',
    currency: 'MXN',
});

const formatMoney = (amount: number): string => formatter.format(amount);

export default formatMoney;
