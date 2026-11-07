import type { FastifyReply, FastifyRequest } from "fastify";
import { findDevice, type Device, type DeviceCatalog } from "../devices.js";
import { colorSchema } from "../schemas/devices.js";
import type { DevicesService } from "../services/devices.js";

type Handler = (request: FastifyRequest, reply: FastifyReply) => Promise<unknown>;

export function createDevicesController(devices: DevicesService, catalog: DeviceCatalog) {
    async function respond(request: FastifyRequest, reply: FastifyReply,
        operation: () => Promise<unknown>, errorMessage: string) {
        try {
            return await operation();
        } catch (error) {
            request.log.error(error);
            return reply.code(502).send({ error: errorMessage });
        }
    }

    // fixedId serves the legacy routes; otherwise the id comes from /devices/:id.
    function withDevice(fixedId: string | undefined,
        run: (device: Device, request: FastifyRequest, reply: FastifyReply) => Promise<unknown>): Handler {
        return async (request, reply) => {
            const id = fixedId ?? (request.params as { id: string }).id;
            const device = findDevice(catalog, id);
            if (!device) return reply.code(404).send({ error: "Unknown device" });
            return run(device, request, reply);
        };
    }

    return {
        getState: (fixedId?: string) => withDevice(fixedId, (device, request, reply) =>
            respond(request, reply, () => devices.getState(device), "Unable to get device state")),
        setColor: (fixedId?: string) => withDevice(fixedId, async (device, request, reply) => {
            if (device.type !== "light") return reply.code(400).send({ error: "Device does not support color" });
            const parsed = colorSchema.safeParse(request.body);
            if (!parsed.success) return reply.code(400).send({ error: "Invalid color or brightness" });
            return respond(request, reply, () => devices.setColor(device, parsed.data),
                "Unable to communicate with Home Assistant");
        }),
        turnOn: (fixedId?: string) => withDevice(fixedId, (device, request, reply) =>
            respond(request, reply, () => devices.turnOn(device), "Unable to turn on device")),
        turnOff: (fixedId?: string) => withDevice(fixedId, (device, request, reply) =>
            respond(request, reply, () => devices.turnOff(device), "Unable to turn off device")),
    };
}
