import { z } from "zod";
import type { Entity } from "../devices.js";
import type { BridgeEnv } from "../schemas/env.js";

const entitySchema = z.object({
    entity_id: z.string(),
    state: z.string(),
    attributes: z.record(z.string(), z.unknown()),
});

// A script as Home Assistant's script editor stores it (/api/config/script/config/<id>).
const scriptSchema = z.object({
    alias: z.string().optional(),
    description: z.string().optional(),
    icon: z.string().optional(),
    sequence: z.array(z.record(z.string(), z.unknown())).default([]),
}).passthrough();
export type ScriptConfig = z.infer<typeof scriptSchema>;

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
        // The script editor's API: writes scripts.yaml and reloads. Callers validate the id.
        async getScriptConfig(id: string): Promise<ScriptConfig | undefined> {
            try {
                return parse(scriptSchema, await (await request(`/api/config/script/config/${id}`)).json());
            } catch (error) {
                if (error instanceof Error && error.message.endsWith("HTTP 404")) return undefined;
                throw error;
            }
        },
        async saveScriptConfig(id: string, config: ScriptConfig) {
            await request(`/api/config/script/config/${id}`, { method: "POST", body: config });
        },
        async deleteScriptConfig(id: string) {
            await request(`/api/config/script/config/${id}`, { method: "DELETE" });
        },
    };
}
export type HomeAssistantService = ReturnType<typeof createHomeAssistantService>;
