import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname } from 'node:path';
import { config } from '../config.js';

/**
 * Estado que debe sobrevivir a un reinicio: los update_id ya procesados (si se
 * pierden, Telegram reintenta y duplicas un gasto) y el último movimiento de cada
 * chat (para /deshacer).
 *
 * ponytail: un JSON en disco, no una base de datos. Son dos llaves y un usuario.
 * OJO: para que aguante un REDEPLOY hay que montar un volumen en Dokploy sobre
 * STATE_FILE; sin volumen, el contenedor nuevo arranca con el archivo vacío.
 */
type State = {
    seenUpdates: number[];
    lastRecords: Record<string, { sheet: string; row: number; summary: string }>;
};

const EMPTY: State = { seenUpdates: [], lastRecords: {} };

function load(): State {
    try {
        return { ...EMPTY, ...JSON.parse(readFileSync(config.STATE_FILE, 'utf-8')) };
    } catch {
        // No existe, está corrupto o no hay permisos: arrancar en blanco es
        // preferible a no arrancar. El costo es un posible duplicado.
        return structuredClone(EMPTY);
    }
}

export const state = load();

export function persist() {
    try {
        mkdirSync(dirname(config.STATE_FILE), { recursive: true });
        writeFileSync(config.STATE_FILE, JSON.stringify(state));
    } catch (error) {
        console.error('No se pudo guardar el estado:', error);
    }
}
