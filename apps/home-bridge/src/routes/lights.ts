import type { FastifyInstance } from "fastify";
import { createLightsController } from "../controllers/lights.js";
import type { LightsService } from "../services/lights.js";

export function registerLightRoutes(app: FastifyInstance, service: LightsService) {
    const controller = createLightsController(service);
    app.get("/lights/monitores", controller.getState);
    app.post("/lights/monitores/color", controller.setColor);
    app.post("/lights/monitores/on", controller.turnOn);
    app.post("/lights/monitores/off", controller.turnOff);
}
