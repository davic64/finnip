import type { FastifyReply, FastifyRequest } from "fastify";
import { findAction, type ActionName } from "../actions.js";
import type { DevicesService } from "../services/devices.js";

type Params = { id?: string; action?: string };

export function createDevicesController(devices: DevicesService) {
    function unavailable(request: FastifyRequest, reply: FastifyReply, error: unknown) {
        request.log.error(error);
        return reply.code(502).send({ error: "Unable to communicate with Home Assistant" });
    }

    return {
        async list(request: FastifyRequest, reply: FastifyReply) {
            try {
                return { devices: await devices.list() };
            } catch (error) {
                return unavailable(request, reply, error);
            }
        },

        // fixedId serves the legacy /lights/monitores routes; otherwise the id comes from the URL.
        get: (fixedId?: string) => async (request: FastifyRequest, reply: FastifyReply) => {
            const id = fixedId ?? (request.params as Params).id!;
            try {
                return (await devices.get(id)) ?? reply.code(404).send({ error: "Unknown device" });
            } catch (error) {
                return unavailable(request, reply, error);
            }
        },

        run: (fixedId?: string) => async (request: FastifyRequest, reply: FastifyReply) => {
            const params = request.params as Params;
            const id = fixedId ?? params.id!;
            const name = params.action!;
            const action = findAction(name);
            if (!action) return reply.code(404).send({ error: "Unknown action" });

            // Validate the body before touching Home Assistant.
            const parsed = action.input.safeParse(request.body ?? {});
            if (!parsed.success) return reply.code(400).send({ error: "Invalid input for action" });
            const input = parsed.data as Record<string, unknown>;

            let device;
            try {
                device = await devices.get(id);
            } catch (error) {
                return unavailable(request, reply, error);
            }
            if (!device) return reply.code(404).send({ error: "Unknown device" });
            if (!device.capabilities.includes(name as ActionName)) {
                return reply.code(400).send({ error: "Action not supported by this device" });
            }
            const problem = action.check?.(input, device);
            if (problem) return reply.code(400).send({ error: problem });

            try {
                return await devices.run(device, name as ActionName, input);
            } catch (error) {
                return unavailable(request, reply, error);
            }
        },
    };
}
