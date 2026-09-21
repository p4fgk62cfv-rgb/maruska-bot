"""
Веб-часть Крокодила: холст как Telegram Mini App.

Работает в том же процессе, что и бот. Railway даёт один порт —
на нём поднимается aiohttp, а бот продолжает опрашивать Telegram.

Endpoints:
    GET  /            — проверка живости
    GET  /draw        — страница холста
    GET  /api/round   — слово для ведущего (по подписи Telegram)
    POST /api/draw    — приём рисунка и отправка его в чат

Доверять данным из браузера нельзя, поэтому каждый запрос несёт
initData от Telegram, а сервер проверяет его подпись ключом бота.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import time
from pathlib import Path
from urllib.parse import parse_qsl

from aiohttp import web

from aiogram.types import BufferedInputFile

from database.repository import get_round_by_token, update_round
from games import state
from games.words import LEVEL_NAMES


logger = logging.getLogger("maruska.webapp")

STATIC_DIR = Path(__file__).parent / "static"

# Подпись Telegram живёт сутки — дольше не принимаем
MAX_AUTH_AGE = 24 * 60 * 60

MAX_IMAGE_BYTES = 6 * 1024 * 1024


def _secret_key(bot_token: str) -> bytes:
    return hmac.new(
        b"WebAppData",
        bot_token.encode(),
        hashlib.sha256,
    ).digest()


def verify_init_data(init_data: str, bot_token: str) -> dict | None:
    """
    Проверяет подпись initData и возвращает разобранные поля.
    None — подпись не сошлась или данные протухли.
    """
    if not init_data:
        return None

    try:
        pairs = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError:
        return None

    received_hash = pairs.pop("hash", None)

    if not received_hash:
        return None

    check_string = "\n".join(
        f"{key}={pairs[key]}" for key in sorted(pairs)
    )

    expected = hmac.new(
        _secret_key(bot_token),
        check_string.encode(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, received_hash):
        return None

    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError:
        return None

    if auth_date and time.time() - auth_date > MAX_AUTH_AGE:
        return None

    try:
        pairs["user"] = json.loads(pairs.get("user", "{}"))
    except json.JSONDecodeError:
        pairs["user"] = {}

    return pairs


async def _authorize(request: web.Request, init_data: str):
    """
    Возвращает (раунд, пользователь) или поднимает HTTP-ошибку.
    """
    parsed = verify_init_data(init_data, request.app["bot_token"])

    if parsed is None:
        raise web.HTTPUnauthorized(text="bad signature")

    user = parsed.get("user") or {}
    user_id = user.get("id")

    if not user_id:
        raise web.HTTPUnauthorized(text="no user")

    token = parsed.get("start_param") or ""

    if not token:
        raise web.HTTPBadRequest(text="no round")

    item = await get_round_by_token(token)

    if item is None or item.status not in ("waiting", "playing"):
        raise web.HTTPNotFound(text="round is over")

    if item.host_telegram_id and item.host_telegram_id != user_id:
        raise web.HTTPForbidden(text="not a host")

    return item, user


# ---------------------------------------------------------
# Хендлеры
# ---------------------------------------------------------

async def health(request: web.Request):
    return web.json_response({"ok": True, "service": "maruska"})


async def draw_page(request: web.Request):
    page = STATIC_DIR / "draw.html"

    if not page.exists():
        raise web.HTTPNotFound(text="page missing")

    return web.FileResponse(page)


async def api_round(request: web.Request):
    init_data = request.headers.get("X-Init-Data", "")
    item, _user = await _authorize(request, init_data)

    return web.json_response({
        "word": item.word or "",
        "level": LEVEL_NAMES.get(item.level or "", ""),
        "status": item.status,
    })


async def api_draw(request: web.Request):
    try:
        payload = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text="bad json")

    init_data = payload.get("initData") or request.headers.get(
        "X-Init-Data", ""
    )

    item, user = await _authorize(request, init_data)

    image = payload.get("image") or ""

    if "," in image:
        image = image.split(",", 1)[1]

    try:
        content = base64.b64decode(image, validate=True)
    except Exception:
        raise web.HTTPBadRequest(text="bad image")

    if not content or len(content) > MAX_IMAGE_BYTES:
        raise web.HTTPBadRequest(text="bad image size")

    bot = request.app["bot"]

    name = user.get("first_name") or user.get("username") or "Ведущий"

    try:
        await bot.send_photo(
            chat_id=item.chat_id,
            photo=BufferedInputFile(content, filename="croc.png"),
            caption=(
                f"🎨 <b>{name}</b> нарисовал. Что это?\n"
                "Пишите варианты в чат."
            ),
        )
    except Exception as error:
        logger.error("DRAW SEND: %s %s", type(error).__name__, error)
        raise web.HTTPBadGateway(text="send failed")

    await update_round(item.id, status="playing")

    current = state.get(item.chat_id)

    if current is not None:
        current.status = "playing"

    return web.json_response({"ok": True})


def create_app(bot, bot_token: str) -> web.Application:
    app = web.Application(client_max_size=MAX_IMAGE_BYTES + 1024 * 1024)

    app["bot"] = bot
    app["bot_token"] = bot_token

    app.router.add_get("/", health)
    app.router.add_get("/draw", draw_page)
    app.router.add_get("/api/round", api_round)
    app.router.add_post("/api/draw", api_draw)

    return app


async def start_web_server(bot, bot_token: str, port: int):
    app = create_app(bot, bot_token)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()

    logger.info("Веб-сервер поднят на порту %s", port)

    return runner


def public_url() -> str:
    """
    Публичный адрес сервиса. Railway отдаёт его в RAILWAY_PUBLIC_DOMAIN,
    но его можно задать и вручную через PUBLIC_URL.
    """
    explicit = os.getenv("PUBLIC_URL", "").strip().rstrip("/")

    if explicit:
        return explicit

    domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()

    if domain:
        return f"https://{domain}"

    return ""
