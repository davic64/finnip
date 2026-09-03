import { Hono } from "hono";
import { config } from "../config.js";
import { handleTelegramUpdate } from "./webhook.service.js";

const webhook = new Hono();

webhook.post('/', async (c) => {
    const secret = c.req.header('x-telegram-bot-api-secret-token');

    if (secret !== config.WEBHOOK_SECRET) {
        return c.text('Unauthorized', 401);
    }

    const update = await c.req.json();

    handleTelegramUpdate(update).catch((error) => {
        console.error('Error processing update:', error);
    });

    return c.text('ok');
})

export default webhook;