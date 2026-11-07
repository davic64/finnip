import { z } from "zod";
import type { Entity } from "../devices.js";
import type { BridgeEnv } from "../schemas/env.js";

const entitySchema = z.object({
    entity_id: z.string(),
    state: z.string(),
    attributes: z.record(z.string(), z.unknown()),
});

export function createHomeAssistantService(env: BridgeEnv, fetchImpl: typeof fetch = fetch) {
    async function request(path: string, init: { method?: string; body?: unknown } = {}) {
        const response = await fetchImpl(`${env.HA_URL}${path}`, {
            method: init.method ?? "GET",
            headers: {
                Authorization: `Bearer ${env.HA_TOKEN}`,
                ...(init.body === undefined ? {} : { "Content-Type": "application/json" }),
            },
            body: init.body === undefined ? undefined : JSON.stringify(init.body),
            signal: AbortSignal.timeout(5000),
        });
        if (!response.ok) throw new Error(`Home Assistant returned HTTP ${response.status}`);
        return response;
    }

    function parse<T>(schema: z.ZodType<T>, value: unknown): T {
        const parsed = schema.safeParse(value);
        if (!parsed.success) throw new Error("Invalid Home Assistant response");
        return parsed.data;
    }

    return {
        // The template API is the REST way to read labels; /api/states does not include them.
        async labeledEntityIds(label: string): Promise<string[]> {
            const response = await request("/api/template", {
                method: "POST",
                body: { template: `{{ label_entities('${label}') | tojson }}` },
            });
            return parse(z.array(z.string()), JSON.parse(await response.text()));
        },
        async getStates(): Promise<Entity[]> {
            return parse(z.array(entitySchema), await (await request("/api/states")).json());
        },
        async getState(entityId: string): Promise<Entity> {
            const entity = parse(entitySchema, await (await request(`/api/states/${entityId}`)).json());
            if (entity.entity_id !== entityId) throw new Error("Home Assistant returned another entity");
            return entity;
        },
        async callService(domain: string, service: string, data: Record<string, unknown>) {
            await request(`/api/services/${domain}/${service}`, { method: "POST", body: data });
        },
    };
}
export type HomeAssistantService = ReturnType<typeof createHomeAssistantService>;
