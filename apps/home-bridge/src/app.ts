import Fastify from "fastify";
import { envSchema } from "./schemas/env.js";
import { createAuthHook } from "./hooks/auth.js";
import { createHomeAssistantService } from "./services/home-assistant.js";
import { createDevicesService } from "./services/devices.js";
import { registerDeviceRoutes } from "./routes/devices.js";
import { registerHealthRoutes } from "./routes/health.js";
import { registerAdminRoutes } from "./routes/admin.js";
import { createAdminService } from "./services/admin.js";
import { createRegistry, type Registry } from "./services/registry.js";
// Construct without listening, so tests exercise the real HTTP stack via inject().
export function buildApp(options: {
    env?: Record<string, unknown>;
    fetchImpl?: typeof fetch;
    logger?: boolean;
    settleMs?: number;
    registry?: Registry;
    labelWaitMs?: number;
} = {}) {
    const env = envSchema.parse(options.env ?? process.env);
    const app = Fastify({ logger: options.logger ?? true });
    const homeAssistant = createHomeAssistantService(env, options.fetchImpl);
    app.addHook("onRequest", createAuthHook(env.BRIDGE_API_KEY));
    registerHealthRoutes(app);
    const devices = createDevicesService(homeAssistant, options.settleMs);
    registerDeviceRoutes(app, devices);
    const registry = options.registry ?? createRegistry(env);
    registerAdminRoutes(app, createAdminService(homeAssistant, registry, devices, options.labelWaitMs));
    return app;
}
