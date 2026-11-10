import { describe, expect, it } from "vitest";
import { createRegistry, type WebSocketLike } from "../src/services/registry.js";

const env = { HA_URL: "http://homeassistant:8123", HA_TOKEN: "test-token", BRIDGE_API_KEY: "a".repeat(32) };

// Speaks Home Assistant's WebSocket protocol: auth, then answers command id 1 with `answer`.
function fakeSocket(answer: (command: Record<string, unknown>) => Record<string, unknown>, token = "test-token") {
    const sent: Record<string, unknown>[] = [];
    const urls: string[] = [];
    let closed = 0;
    class FakeWebSocket {
        onmessage: ((event: { data: unknown }) => void) | null = null;
        onerror: ((event: unknown) => void) | null = null;
        constructor(url: string) {
            urls.push(url);
            queueMicrotask(() => this.reply({ type: "auth_required" }));
        }
        private reply(data: unknown) {
            this.onmessage?.({ data: JSON.stringify(data) });
        }
        send(raw: string) {
            const data = JSON.parse(raw);
            sent.push(data);
            if (data.type === "auth") return this.reply({ type: data.access_token === token ? "auth_ok" : "auth_invalid" });
            queueMicrotask(() => this.reply({ type: "result", id: data.id, ...answer(data) }));
        }
        close() {
            closed++;
        }
    }
    return { Impl: FakeWebSocket as unknown as WebSocketLike, sent, urls, closed: () => closed };
}

describe("entity registry over WebSocket", () => {
    it("authenticates, sends one command and closes", async () => {
        const ws = fakeSocket(() => ({ success: true, result: { labels: ["finnip", "sala"] } }));
        const registry = createRegistry(env, ws.Impl);
        expect(await registry.getLabels("light.lampara")).toEqual(["finnip", "sala"]);
        expect(ws.urls).toEqual(["ws://homeassistant:8123/api/websocket"]);
        expect(ws.sent).toEqual([
            { type: "auth", access_token: "test-token" },
            { id: 1, type: "config/entity_registry/get", entity_id: "light.lampara" },
        ]);
        expect(ws.closed()).toBe(1);
    });

    it("updates labels", async () => {
        const ws = fakeSocket(() => ({ success: true, result: {} }));
        await createRegistry(env, ws.Impl).setLabels("light.lampara", ["sala", "finnip"]);
        expect(ws.sent[1]).toEqual({ id: 1, type: "config/entity_registry/update", entity_id: "light.lampara", labels: ["sala", "finnip"] });
    });

    it("reports Home Assistant's error with its code", async () => {
        const ws = fakeSocket(() => ({ success: false, error: { code: "not_found", message: "Entity not found" } }));
        await expect(createRegistry(env, ws.Impl).getLabels("light.x")).rejects.toMatchObject({ code: "not_found" });
    });

    it("fails on a rejected token and on a timeout", async () => {
        await expect(createRegistry(env, fakeSocket(() => ({}), "other").Impl).getLabels("light.x")).rejects.toThrow(/rejected the token/);
        class Silent {
            onmessage = null;
            onerror = null;
            send() {}
            close() {}
        }
        await expect(createRegistry(env, Silent as unknown as WebSocketLike, 20).getLabels("light.x")).rejects.toThrow(/timed out/);
    });
});
