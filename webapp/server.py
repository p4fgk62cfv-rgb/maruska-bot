"""
Веб-часть Крокодила: холст как Telegram Mini App.

Работает в том же процессе, что и бот. Railway даёт один порт —
на нём поднимается aiohttp, а бот продолжает опрашивать Telegram.

Endpoints:
    GET  /            — проверка живости
    GET  /draw        — страница холста
    GET  /api/round   — слово для ведущего (по подписи Telegram)
    POST /api/draw    — приём рисунка и отправка его в чат
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

from aiogram.types import BufferedInputFile, InputMediaPhoto

from database.repository import get_round_by_token, update_round
from games import state
from games.crocodile import drawing_keyboard, ensure_hint_message

from webapp.admin import setup_admin_routes
from webapp.admin_v2 import setup_v2_routes
from webapp.fishing_api import setup_fishing_routes
from webapp.arena_admin import setup_arena_admin_routes
from games.words import LEVEL_NAMES


logger = logging.getLogger("maruska.webapp")

STATIC_DIR = Path(__file__).parent / "static"

MAX_AUTH_AGE = 24 * 60 * 60
MAX_IMAGE_BYTES = 6 * 1024 * 1024


def _secret_key(bot_token: str) -> bytes:
    return hmac.new(
        b"WebAppData",
        bot_token.encode(),
        hashlib.sha256,
    ).digest()


def verify_init_data(init_data: str, bot_token: str) -> dict | None:
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


async def health(request: web.Request):
    return web.json_response({"ok": True, "service": "maruska"})


NO_CACHE = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}

ASSET_TYPES = {
    ".css": "text/css",
    ".js": "application/javascript",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def _page_with_version(page) -> web.Response:
    import changelog

    html = page.read_text(encoding="utf-8")
    html = html.replace("__MARA_VERSION__", str(changelog.latest().version))

    return web.Response(
        text=html,
        content_type="text/html",
        charset="utf-8",
        headers=NO_CACHE,
    )


async def fishing_asset(request: web.Request):
    """
    Static assets for Fishing.

    /fishing-assets/app.js
    /fishing-assets/styles.css
        -> webapp/static/fishing/

    /fishing-assets/<asset>
        -> webapp/static/fishing/assets/fishing/
    """
    name = request.match_info["path"]

    if not name or ".." in Path(name).parts:
        raise web.HTTPNotFound()

    # The HTML loads these two files directly from /fishing-assets/.
    # Fish/location/bait/gear images live under /fishing-assets/<folder>/.
    if name in {"app.js", "styles.css", "server.js"}:
        root = STATIC_DIR / "fishing"
    else:
        root = STATIC_DIR / "fishing" / "assets" / "fishing"

    path = root / name

    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        raise web.HTTPNotFound()

    if not path.is_file():
        raise web.HTTPNotFound()

    # Картинки игры (10+ МБ) кэшируются на неделю — иначе телефон скачивает
    # их заново при каждом открытии. Код и стили — без кэша, чтобы
    # обновления доходили сразу.
    if name in {"app.js", "styles.css", "server.js"}:
        return web.FileResponse(path, headers=NO_CACHE)

    return web.FileResponse(path, headers={"Cache-Control": "public, max-age=604800"})


async def admin_asset(request: web.Request):
    name = request.match_info["name"]

    if "/" in name or ".." in name:
        raise web.HTTPNotFound()

    path = STATIC_DIR / "admin" / name
    kind = ASSET_TYPES.get(path.suffix)

    if kind is None or not path.is_file():
        raise web.HTTPNotFound()

    if kind.startswith("image/"):
        return web.Response(
            body=path.read_bytes(),
            content_type=kind,
            headers=NO_CACHE,
        )

    return web.Response(
        text=path.read_text(encoding="utf-8"),
        content_type=kind,
        charset="utf-8",
        headers=NO_CACHE,
    )


async def fishing_page(request: web.Request):
    page = STATIC_DIR / "fishing" / "index.html"
    if not page.exists():
        raise web.HTTPNotFound(text="fishing page missing")
    return _page_with_version(page)


async def admin_page(request: web.Request):
    page = STATIC_DIR / "admin.html"

    if not page.exists():
        raise web.HTTPNotFound(text="page missing")

    return _page_with_version(page)


async def draw_page(request: web.Request):
    page = STATIC_DIR / "draw.html"

    if not page.exists():
        raise web.HTTPNotFound(text="page missing")

    return _page_with_version(page)


async def api_round(request: web.Request):
    init_data = request.headers.get("X-Init-Data", "")
    item, _user = await _authorize(request, init_data)

    drawings = request.app["drawings"]

    return web.json_response({
        "word": item.word or "",
        "level": LEVEL_NAMES.get(item.level or "", ""),
        "status": item.status,
        "has_drawing": item.id in drawings,
    })


async def api_drawing(request: web.Request):
    init_data = request.headers.get("X-Init-Data", "")
    item, _user = await _authorize(request, init_data)

    content = request.app["drawings"].get(item.id)

    if not content:
        raise web.HTTPNotFound(text="no drawing")

    return web.Response(body=content, content_type="image/png")


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

    request.app["drawings"][item.id] = content

    preview = bool(payload.get("preview"))
    live = request.app["live_messages"]
    message_id = live.get(item.id)

    caption = (
        f"🖼 <b>{name}</b> делает первые штрихи…"
        if preview
        else f"🎨 <b>{name}</b> нарисовал. Что это?\nПишите варианты в чат."
    )

    markup = (
        None
        if preview
        else drawing_keyboard(item.id, item.token or "", item.likes or 0)
    )

    try:
        if message_id:
            await bot.edit_message_media(
                chat_id=item.chat_id,
                message_id=message_id,
                media=InputMediaPhoto(
                    media=BufferedInputFile(content, filename="croc.png"),
                    caption=caption,
                ),
                reply_markup=markup,
            )
        else:
            sent = await bot.send_photo(
                chat_id=item.chat_id,
                photo=BufferedInputFile(content, filename="croc.png"),
                caption=caption,
                reply_markup=markup,
            )
            live[item.id] = sent.message_id
    except Exception as error:
        logger.error("DRAW SEND: %s %s", type(error).__name__, error)

        if message_id:
            live.pop(item.id, None)
            try:
                sent = await bot.send_photo(
                    chat_id=item.chat_id,
                    photo=BufferedInputFile(content, filename="croc.png"),
                    caption=caption,
                    reply_markup=markup,
                )
                live[item.id] = sent.message_id
            except Exception:
                raise web.HTTPBadGateway(text="send failed")
        else:
            raise web.HTTPBadGateway(text="send failed")

    if not preview:
        live.pop(item.id, None)
        await ensure_hint_message(bot, state.get(item.chat_id))

    await update_round(item.id, status="playing")

    current = state.get(item.chat_id)

    if current is not None:
        current.status = "playing"

    return web.json_response({"ok": True, "preview": preview})


def create_app(bot, bot_token: str) -> web.Application:
    app = web.Application(client_max_size=MAX_IMAGE_BYTES + 1024 * 1024)

    import time as _time

    app["bot"] = bot
    app["bot_token"] = bot_token
    app["started_at"] = _time.time()
    app["drawings"] = {}
    app["live_messages"] = {}

    app.router.add_get("/", health)
    app.router.add_get("/draw", draw_page)
    app.router.add_get("/fishing", fishing_page)
    app.router.add_get("/admin", admin_page)
    app.router.add_get("/api/round", api_round)
    app.router.add_get("/api/drawing", api_drawing)
    app.router.add_post("/api/draw", api_draw)

    setup_admin_routes(app)
    setup_v2_routes(app)
    setup_fishing_routes(app)
    setup_arena_admin_routes(app)

    app.router.add_get("/admin-assets/{name}", admin_asset)
    app.router.add_get("/fishing-assets/{path:.*}", fishing_asset)

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
    explicit = os.getenv("PUBLIC_URL", "").strip().rstrip("/")

    if explicit:
        return explicit

    domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()

    if domain:
        return f"https://{domain}"

    return ""
