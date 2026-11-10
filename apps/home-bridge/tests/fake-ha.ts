import type { Entity } from "../src/devices.js";

type Call = { method: string; path: string; body: unknown; headers: Record<string, string> };

// Routes requests like Home Assistant's REST API so tests don't depend on call order.
export function fakeHomeAssistant(options: {
    entities: Entity[];
    labeled: string[];
    // Mutates entities to simulate what the device reports after a service call.
    onService?: (domain: string, service: string, body: Record<string, unknown>, entities: Map<string, Entity>) => void;
    // Return a Response (or throw) to simulate a failure on a given request.
    fail?: (method: string, path: string) => Response | undefined;
    // Script editor configs by id; saving one also creates its script.<id> entity, like a reload.
    scripts?: Record<string, Record<string, unknown>>;
}) {
    const scripts = new Map(Object.entries(structuredClone(options.scripts ?? {})));
    const entities = new Map(options.entities.map((entity) => [entity.entity_id, structuredClone(entity)]));
    for (const [id, config] of scripts) {
        if (!entities.has(`script.${id}`)) entities.set(`script.${id}`, { entity_id: `script.${id}`, state: "off", attributes: { friendly_name: config.alias } });
    }
    const calls: Call[] = [];
    const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

    const fetchImpl: typeof fetch = async (input, init) => {
        const path = new URL(String(input)).pathname;
        const method = init?.method ?? "GET";
        const body = typeof init?.body === "string" ? JSON.parse(init.body) : undefined;
        calls.push({ method, path, body, headers: init?.headers as Record<string, string> });

        const failure = options.fail?.(method, path);
        if (failure) return failure;
        if (method === "POST" && path === "/api/template") return new Response(JSON.stringify(options.labeled));
        if (method === "GET" && path === "/api/states") return json([...entities.values()]);
        const state = /^\/api\/states\/(.+)$/.exec(path);
        if (method === "GET" && state) {
            const entity = entities.get(state[1]!);
            return entity ? json(entity) : json({ message: "Entity not found." }, 404);
        }
        const script = /^\/api\/config\/script\/config\/(\w+)$/.exec(path);
        if (script) {
            const id = script[1]!;
            if (method === "POST") {
                scripts.set(id, body);
                entities.set(`script.${id}`, { entity_id: `script.${id}`, state: "off", attributes: { friendly_name: body.alias } });
                return json({ result: "ok" });
            }
            if (!scripts.has(id)) return json({ message: "Resource not found" }, 404);
            if (method === "DELETE") {
                scripts.delete(id);
                entities.delete(`script.${id}`);
                return json({ result: "ok" });
            }
            return json(scripts.get(id));
        }
        const service = /^\/api\/services\/(\w+)\/(\w+)$/.exec(path);
        if (method === "POST" && service) {
            options.onService?.(service[1]!, service[2]!, body, entities);
            return json([]);
        }
        return json({ message: "Not found" }, 404);
    };

    return {
        fetchImpl,
        calls,
        serviceCalls: () => calls.filter((call) => call.path.startsWith("/api/services/")),
        scripts,
    };
}

export const set = (entities: Map<string, Entity>, id: string, state: string, attributes: Record<string, unknown> = {}) => {
    const entity = entities.get(id)!;
    entities.set(id, { ...entity, state, attributes: { ...entity.attributes, ...attributes } });
};
