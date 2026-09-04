import { config } from '../config.js';

// Siempre en la zona del usuario: el contenedor corre en UTC y un gasto de las
// 7pm en México se guardaría con la fecha del día siguiente.
const formatter = new Intl.DateTimeFormat('es-MX', {
    timeZone: config.TIMEZONE,
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
});

/** Fecha en dd/MM/yyyy, que es como viven las fechas en la hoja. */
const formatDate = (date: Date = new Date()): string => formatter.format(date);

export default formatDate;
