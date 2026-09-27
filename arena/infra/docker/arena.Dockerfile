# Маруська Арена: API + WebSocket + собранный фронтенд в одном образе.
# Build context — папка arena/:  docker build -f infra/docker/arena.Dockerfile .
FROM node:22-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
COPY apps/api/package.json apps/api/
COPY apps/web/package.json apps/web/
COPY packages/game-engine/package.json packages/game-engine/
COPY packages/shared/package.json packages/shared/
COPY packages/ui/package.json packages/ui/
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build && npm prune --omit=dev --no-audit --no-fund

FROM node:22-slim
ENV NODE_ENV=production \
    WEB_DIST=../web/dist
WORKDIR /app
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/package.json ./
COPY --from=build /app/apps/web/dist ./apps/web/dist
COPY --from=build /app/apps/api/package.json /app/apps/api/prisma.config.ts ./apps/api/
COPY --from=build /app/apps/api/prisma ./apps/api/prisma
COPY --from=build /app/apps/api/dist ./apps/api/dist
WORKDIR /app/apps/api
USER node
EXPOSE 8080
# Migrations only touch the "arena" schema; the bot's tables in "public" are never altered.
CMD ["sh", "-c", "npx prisma migrate deploy && exec node dist/main.js"]
