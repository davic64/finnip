import { timingSafeEqual } from "node:crypto";
import type { FastifyReply, FastifyRequest } from "fastify";

export function createAuthHook(apiKey: string) {
    const expected = Buffer.from(apiKey);
    return async (request: FastifyRequest, reply: FastifyReply) => {
        if (request.url === "/health") return;
        const provided = Buffer.from(request.headers.authorization?.replace(/^Bearer /, "") ?? "");
        if (expected.length !== provided.length || !timingSafeEqual(expected, provided)) {
            return reply.code(401).send({ error: "Unauthorized" });
        }
    };
}
