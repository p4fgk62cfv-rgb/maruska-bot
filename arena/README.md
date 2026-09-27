# Маруська Арена

Дурак онлайн — Telegram Mini App бота Маруська. Архитектура: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Локально

```bash
cd arena
npm install
cp .env.example apps/api/.env      # BOT_TOKEN, SESSION_SECRET, DATABASE_URL (…?schema=arena), DEV_AUTH=1
cd apps/api && npx prisma migrate deploy && cd ../..
npm run dev:api                    # :8080
npm run dev:web                    # :5173, /api проксируется на :8080
```

Вне Telegram, при `DEV_AUTH=1` и в dev-сборке, на стартовом экране есть кнопки «Игрок 1» и «Игрок 2». Они подписывают initData настоящим токеном бота, так что проверка идёт по тому же пути, что и в production.

Или всё сразу в Docker: `docker compose -f infra/docker/docker-compose.yml up --build` (переменные берутся из `arena/.env`).

## Проверки

```bash
npm run typecheck
npm test                                                     # движок + unit-тесты API
TEST_DATABASE_URL='postgresql://…/maruska?schema=arena' npm test   # + интеграция с Postgres (деньги, авторизация)
```

## Деплой на Railway

1. Новый сервис из этого же репозитория: Root Directory `arena`, Dockerfile Path `infra/docker/arena.Dockerfile`.
2. Переменные: `BOT_TOKEN` (тот же, что у бота), `BOT_USERNAME`, `DATABASE_URL` = URL базы бота + `?schema=arena`, `SESSION_SECRET` (`openssl rand -hex 32`), с этапа 2 — `REDIS_URL` (плагин Redis).
3. Сгенерировать домен сервиса.
4. BotFather → `/newapp` (или Bot Settings → Configure Mini App) → URL = домен арены. Короткое имя приложения записать в `MINI_APP_SHORT_NAME` (арена) и `ARENA_APP_NAME` (бот).
5. У бота задать `ARENA_URL` = домен арены. После этого `/game` покажет кнопку «🎮 Играть».

Миграции выполняются при старте контейнера и затрагивают только схему `arena`.
