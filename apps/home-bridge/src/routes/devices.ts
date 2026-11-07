import type { FastifyInstance } from "fastify";
import { createDevicesController } from "../controllers/devices.js";
import type { DevicesService } from "../services/devices.js";

// Kept so older finnip_lights versions keep working; still requires the HA label.
const LEGACY_DEVICE = "light.leds_monitores";

export function registerDeviceRoutes(app: FastifyInstance, service: DevicesService) {
    const controller = createDevicesController(service);
    app.get("/devices", controller.list);
    app.get("/devices/:id", controller.get());
    app.post("/devices/:id/:action", controller.run());

    app.get("/lights/monitores", controller.get(LEGACY_DEVICE));
    app.post("/lights/monitores/:action", controller.run(LEGACY_DEVICE));
}
