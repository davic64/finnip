FROM node:24-alpine AS build
RUN corepack enable

ENV CI=true

WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm build

FROM node:24-alpine
RUN corepack enable

ENV CI=true

WORKDIR /app
COPY --from=build /app/dist ./dist
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --prod --frozen-lockfile

EXPOSE 8787
CMD ["node", "dist/index.js"]