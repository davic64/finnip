import type { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";
import { z } from "zod";
import { Refused, type AdminService } from "../services/admin.js";

const modeBody = z.object({
    name: z.string().trim().min(1).max(60).optional(),
    music: z.boolean().default(true),
    steps: z.array(z.object({
        device: z.string().min(1).max(100),
        action: z.string().min(1).max(40),
        params: z.record(z.string(), z.unknown()).default({}),
    })).min(1).max(30),
});

// Exposing devices and managing modes (scripts modo_*): every limit is enforced in services/admin.ts.
export function registerAdminRoutes(app: FastifyInstance, admin: AdminService) {
    const handle = (work: (request: FastifyRequest) => Promise<unknown>) =>
        async (request: FastifyRequest, reply: FastifyReply) => {
            try {
                return await work(request);
            } catch (error) {
                if (error instanceof Refused) return reply.code(error.status).send({ error: error.message });
                request.log.error(error);
                return reply.code(502).send({ error: "Unable to communicate with Home Assistant" });
            }
        };
    const param = (request: FastifyRequest, key: string) => (request.params as Record<string, string>)[key]!;

    app.get("/candidates", handle(async () => ({ candidates: await admin.candidates() })));
    app.post("/devices/:id/expose", handle((request) => admin.expose(param(request, "id"))));
    app.post("/devices/:id/hide", handle((request) => admin.hide(param(request, "id"))));
    app.get("/modes", handle(async () => ({ modes: await admin.modes() })));
    app.get("/modes/:slug", handle((request) => admin.mode(param(request, "slug"))));
    app.put("/modes/:slug", handle(async (request) => {
        const body = modeBody.safeParse(request.body ?? {});
        if (!body.success) throw new Refused(400, "Modo inválido: hacen falta pasos {device, action, params}");
        return admin.save(param(request, "slug"), body.data);
    }));
    app.delete("/modes/:slug", handle((request) => admin.remove(param(request, "slug"))));
}
