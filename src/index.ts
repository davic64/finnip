import { serve } from '@hono/node-server'
import { Hono } from 'hono'
import { config } from './config.js'
import webhook from './webhook/webhook.routes.js'

const app = new Hono()

app.route('/webhook', webhook)

app.get('/', (c) => {
  return c.text('Hello Finnip!')
})

serve({
  fetch: app.fetch,
  hostname: '0.0.0.0',
  port: config.PORT,
}, (info) => {
  console.log(`Server is running on http://localhost:${info.port}`)
})
