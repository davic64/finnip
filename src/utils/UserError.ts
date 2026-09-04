/**
 * Error cuyo mensaje SÍ se le puede enseñar al usuario tal cual.
 * Cualquier otro error se le muestra como un mensaje genérico.
 */
export class UserError extends Error { }

export const toUserMessage = (error: unknown): string =>
    error instanceof UserError
        ? error.message
        : 'Algo se rompió de mi lado 😖 Vuelve a intentarlo en un minuto.';
