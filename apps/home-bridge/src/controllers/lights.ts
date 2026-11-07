import type { FastifyReply, FastifyRequest } from "fastify";
import { colorSchema } from "../schemas/lights.js";
import type { LightsService } from "../services/lights.js";

export function createLightsController(lights: LightsService) {
    async function respond(request: FastifyRequest, reply: FastifyReply,
        operation: () => Promise<unknown>, errorMessage: string) {
        try {
            return await operation();
        } catch (error) {
            request.log.error(error);
            return reply.code(502).send({ error: errorMessage });
        }
    }
    return {
        getState: (request: FastifyRequest, reply: FastifyReply) =>
            respond(request, reply, lights.getState, "Unable to get light state"),
        setColor(request: FastifyRequest, reply: FastifyReply) {
            const parsed = colorSchema.safeParse(request.body);
            if (!parsed.success) return reply.code(400).send({ error: "Invalid color or brightness" });
            return respond(request, reply, () => lights.setColor(parsed.data),
                "Unable to communicate with Home Assistant");
        },
        turnOn: (request: FastifyRequest, reply: FastifyReply) =>
            respond(request, reply, lights.turnOn, "Unable to turn on lights"),
        turnOff: (request: FastifyRequest, reply: FastifyReply) =>
            respond(request, reply, lights.turnOff, "Unable to turn off lights"),
    };
}
