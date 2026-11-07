import type { FastifyInstance } from "fastify";
import { createDevicesController } from "../controllers/devices.js";
import type { DeviceCatalog } from "../devices.js";
import type { DevicesService } from "../services/devices.js";

export function registerDeviceRoutes(app: FastifyInstance, service: DevicesService, catalog: DeviceCatalog) {
    const controller = createDevicesController(service, catalog);
    app.get("/devices/:id", controller.getState());
    app.post("/devices/:id/color", controller.setColor());
    app.post("/devices/:id/on", controller.turnOn());
    app.post("/devices/:id/off", controller.turnOff());

    // Legacy routes used by the finnip_lights plugin.
    app.get("/lights/monitores", controller.getState("monitorLeds"));
    app.post("/lights/monitores/color", controller.setColor("monitorLeds"));
    app.post("/lights/monitores/on", controller.turnOn("monitorLeds"));
    app.post("/lights/monitores/off", controller.turnOff("monitorLeds"));
}
