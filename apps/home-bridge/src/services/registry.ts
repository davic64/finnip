import type { BridgeEnv } from "../schemas/env.js";

// Home Assistant's entity registry over WebSocket: labels have no REST API (HA 2026.11).
// One short connection per call (labels change rarely): authenticate, one command, close.
type Socket = {
    onmessage: ((event: { data: unknown }) => void) | null;
    onerror: ((event: unknown) => void) | null;
    send(data: string): void;
    close(): void;
};
export type WebSocketLike = new (url: string) => Socket;

export class RegistryError extends Error {
    constructor(message: string, readonly code?: string) {
        super(message);
    }
}

export function createRegistry(
    env: BridgeEnv,
    Impl: WebSocketLike = globalThis.WebSocket as unknown as WebSocketLike,
    timeoutMs = 5000,
) {
    const url = `${env.HA_URL.replace(/^http/, "ws")}/api/websocket`;

    function command<T>(message: Record<string, unknown>): Promise<T> {
        return new Promise((resolve, reject) => {
            const ws = new Impl(url);
            const finish = (settle: () => void) => {
                clearTimeout(timer);
                ws.close();
                settle();
            };
            const timer = setTimeout(() => finish(() => reject(new RegistryError("Home Assistant registry timed out"))), timeoutMs);
            ws.onerror = () => finish(() => reject(new RegistryError("Home Assistant registry unreachable")));
            ws.onmessage = (event) => {
                const data = JSON.parse(String(event.data));
                if (data.type === "auth_required") ws.send(JSON.stringify({ type: "auth", access_token: env.HA_TOKEN }));
                else if (data.type === "auth_invalid") finish(() => reject(new RegistryError("Home Assistant rejected the token")));
                else if (data.type === "auth_ok") ws.send(JSON.stringify({ id: 1, ...message }));
                else if (data.type === "result" && data.id === 1) {
                    finish(() => data.success
                        ? resolve(data.result as T)
                        : reject(new RegistryError(data.error?.message ?? "Home Assistant registry error", data.error?.code)));
                }
            };
        });
    }

    return {
        /** Labels of an entity; RegistryError code "not_found" when it has no registry entry. */
        async getLabels(entityId: string): Promise<string[]> {
            const entry = await command<{ labels?: string[] }>({ type: "config/entity_registry/get", entity_id: entityId });
            return entry.labels ?? [];
        },
        async setLabels(entityId: string, labels: string[]): Promise<void> {
            await command({ type: "config/entity_registry/update", entity_id: entityId, labels });
        },
    };
}
export type Registry = ReturnType<typeof createRegistry>;
