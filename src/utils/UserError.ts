import { APIConnectionError } from 'openai';

/**
 * Error cuyo mensaje SÍ se le puede enseñar al usuario tal cual.
 * Cualquier otro error se le muestra como un mensaje genérico.
 */
export class UserError extends Error { }

export const toUserMessage = (error: unknown): string => {
    if (error instanceof UserError) {
        return error.message;
    }

    // DeepSeek se cae o se tarda por rachas. No es que algo se haya roto aquí:
    // el mismo mensaje, tal cual, funciona al reintentar.
    if (error instanceof APIConnectionError) {
        return 'La IA anda lenta ahorita 🐢 Mándamelo otra vez en un minuto.';
    }

    return 'Algo se rompió de mi lado 😖 Vuelve a intentarlo en un minuto.';
};
