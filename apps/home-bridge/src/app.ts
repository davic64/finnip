import Fastify from "fastify";
import { envSchema } from "./schemas/env.js";
import { createAuthHook } from "./hooks/auth.js";
import { createHomeAssistantService } from "./services/home-assistant.js";
import { createLightsService } from "./services/lights.js";
import { registerLightRoutes } from "./routes/lights.js";
import { registerHealthRoutes } from "./routes/health.js";

// Construct without listening, so tests exercise the real HTTP stack via inject().
export function buildApp(options: {
    env?: Record<string, unknown>;
    fetchImpl?: typeof fetch;
    logger?: boolean;
} = {}) {
    const env = envSchema.parse(options.env ?? process.env);
    const app = Fastify({ logger: options.logger ?? true });
    const homeAssistant = createHomeAssistantService(env, options.fetchImpl);
    app.addHook("onRequest", createAuthHook(env.BRIDGE_API_KEY));
    registerHealthRoutes(app);
    registerLightRoutes(app, createLightsService(homeAssistant));
    return app;
}
