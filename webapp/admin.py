"""
API веб-панели.

Вход — через Telegram: панель открывается как Mini App, и Telegram
сам сообщает, кто пришёл. Пароля нет намеренно: публичная админка
с паролем рано или поздно подбирается, а тут подпись проверяется
ключом бота, и подделать её нельзя.

Права: человек видит только те группы, где он администратор.
Владельцы бота из OWNER_IDS видят все.
"""

import logging
import time

from aiohttp import web

from database.repository import (
    achievements_stats,
    block_user,
    game_stats,
    media_stats,
    recent_transactions,
    shop_stats,
    system_counts,
    top_by,
    unlock_achievement,
    change_balance,
    get_blocked_ids,
    get_daily_series,
    get_group_settings,
    get_overview,
    get_user_card,
    list_known_chats,
    list_members,
    set_group_setting,
    unblock_user,
    award_xp,
)

import logging_setup

from actions.catalog import ACTIONS
from actions.phrases import CATEGORY_PHRASES, CALLS, PAIR

from economy.shop import CATEGORIES, ITEMS, category_title

from progress.achievements import ACHIEVEMENTS

from settings import store
from settings.handler import ADMIN_STATUSES, is_owner
from settings.registry import (
    CHOICE_BY_KEY,
    CHOICES,
    FEATURES,
    NUMBER_BY_KEY,
    NUMBERS,
    TEXT_BY_KEY,
    TEXTS,
    groups as setting_groups,
    option_label,
)


logger = logging.getLogger("maruska.admin")


# Кэш прав: проверка администраторства дергает Telegram,
# и делать это на каждый запрос панели незачем.
ACCESS_TTL = 300

_access_cache: dict[int, tuple[float, list[dict]]] = {}


async def visible_chats(bot, user_id: int) -> list[dict]:
    """
    Группы, которыми этот человек вправе управлять.
    """
    cached = _access_cache.get(user_id)

    if cached and time.monotonic() - cached[0] < ACCESS_TTL:
        return cached[1]

    chats = await list_known_chats()

    if is_owner(user_id):
        allowed = chats
    else:
        allowed = []

        for chat in chats:
            try:
                member = await bot.get_chat_member(chat["chat_id"], user_id)
            except Exception:
                continue

            if member.status in ADMIN_STATUSES:
                allowed.append(chat)

    _access_cache[user_id] = (time.monotonic(), allowed)

    return allowed


def drop_access_cache(user_id: int) -> None:
    _access_cache.pop(user_id, None)


async def require_admin(request: web.Request):
    """
    Возвращает (пользователь, доступные группы) или бросает 401/403.
    """
    from webapp.server import verify_init_data

    init_data = request.headers.get("X-Init-Data", "")

    parsed = verify_init_data(init_data, request.app["bot_token"])

    if parsed is None:
        raise web.HTTPUnauthorized(text="bad signature")

    user = parsed.get("user") or {}

    if not user.get("id"):
        raise web.HTTPUnauthorized(text="no user")

    chats = await visible_chats(request.app["bot"], user["id"])

    if not chats and not is_owner(user["id"]):
        raise web.HTTPForbidden(text="not an admin anywhere")

    return user, chats


def _requested_chat(request: web.Request, chats: list[dict]) -> int | None:
    """
    Какую группу смотрим. Пусто — сводка по всем доступным.
    """
    raw = request.query.get("chat_id", "").strip()

    if not raw:
        return None

    try:
        chat_id = int(raw)
    except ValueError:
        raise web.HTTPBadRequest(text="bad chat_id")

    if chat_id not in {chat["chat_id"] for chat in chats}:
        raise web.HTTPForbidden(text="no access to this chat")

    return chat_id


async def _ensure_settings_loaded(chat_id: int) -> None:
    if not store.is_loaded(chat_id):
        try:
            store.prime(chat_id, await get_group_settings(chat_id))
        except Exception:
            store.prime(chat_id, {})


# ---------------------------------------------------------
# Эндпоинты
# ---------------------------------------------------------

async def api_session(request: web.Request):
    user, chats = await require_admin(request)

    return web.json_response({
        "user": {
            "id": user["id"],
            "name": user.get("first_name") or user.get("username") or "Админ",
            "username": user.get("username"),
            "photo": user.get("photo_url"),
            "owner": is_owner(user["id"]),
        },
        "chats": chats,
    })


async def api_overview(request: web.Request):
    _user, chats = await require_admin(request)
    chat_id = _requested_chat(request, chats)

    days = request.query.get("days", "7")
    days = int(days) if days.isdigit() and 1 <= int(days) <= 90 else 7

    totals = await get_overview(chat_id)
    series = await get_daily_series(chat_id, days)

    return web.json_response({
        "totals": totals,
        "series": series,
        "chats_count": len(chats),
    })


async def api_settings(request: web.Request):
    _user, chats = await require_admin(request)
    chat_id = _requested_chat(request, chats)

    if chat_id is None:
        raise web.HTTPBadRequest(text="chat_id required")

    await _ensure_settings_loaded(chat_id)

    values = store.values(chat_id)

    payload = {"sections": []}

    for name in setting_groups():
        section = {"name": name, "items": []}

        for feature in FEATURES:
            if feature.group != name:
                continue

            section["items"].append({
                "kind": "toggle",
                "key": feature.key,
                "title": feature.title,
                "emoji": feature.emoji,
                "description": feature.description,
                "value": bool(values.get(feature.key, feature.default)),
            })

        for choice in CHOICES:
            if choice.group != name:
                continue

            current = values.get(choice.key, choice.default)

            section["items"].append({
                "kind": "choice",
                "key": choice.key,
                "title": choice.title,
                "emoji": choice.emoji,
                "description": choice.description,
                "value": current,
                "label": option_label(choice.key, current),
                "options": [
                    {"value": value, "label": label, "emoji": emoji}
                    for value, label, emoji in choice.options
                ],
            })

        for number in NUMBERS:
            if number.group != name:
                continue

            current = store.get_number(chat_id, number.key)

            section["items"].append({
                "kind": "number",
                "key": number.key,
                "title": number.title,
                "emoji": number.emoji,
                "description": number.description,
                "value": current,
                "label": number.label(current),
                "min": number.minimum,
                "max": number.maximum,
                "step": number.step,
                "unit": number.unit,
            })

        for text in TEXTS:
            if text.group != name:
                continue

            current = store.get_text(chat_id, text.key)

            section["items"].append({
                "kind": "text",
                "key": text.key,
                "title": text.title,
                "emoji": text.emoji,
                "description": text.description,
                "value": current,
                "custom": current != text.default,
                "placeholders": list(text.placeholders),
                "max_length": text.max_length,
            })

        if section["items"]:
            payload["sections"].append(section)

    return web.json_response(payload)


async def api_set_setting(request: web.Request):
    _user, chats = await require_admin(request)

    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text="bad json")

    raw_chat = body.get("chat_id")

    try:
        chat_id = int(raw_chat)
    except (TypeError, ValueError):
        raise web.HTTPBadRequest(text="bad chat_id")

    if chat_id not in {chat["chat_id"] for chat in chats}:
        raise web.HTTPForbidden(text="no access to this chat")

    key = body.get("key")
    value = body.get("value")

    await _ensure_settings_loaded(chat_id)

    # Приводим значение к типу настройки и проверяем его
    if key in NUMBER_BY_KEY:
        try:
            value = NUMBER_BY_KEY[key].clamp(int(value))
        except (TypeError, ValueError):
            raise web.HTTPBadRequest(text="bad number")

    elif key in CHOICE_BY_KEY:
        allowed = {option[0] for option in CHOICE_BY_KEY[key].options}

        if value not in allowed:
            raise web.HTTPBadRequest(text="bad option")

    elif key in TEXT_BY_KEY:
        text = TEXT_BY_KEY[key]

        if not isinstance(value, str) or not value.strip():
            raise web.HTTPBadRequest(text="empty text")

        value = value[: text.max_length]

    elif key in {feature.key for feature in FEATURES}:
        value = bool(value)

    else:
        raise web.HTTPBadRequest(text="unknown key")

    store.apply(chat_id, key, value)

    try:
        await set_group_setting(chat_id=chat_id, key=key, value=value)
    except Exception as error:
        logger.error("ADMIN SAVE: %s %s", type(error).__name__, error)
        raise web.HTTPBadGateway(text="save failed")

    return web.json_response({"ok": True, "key": key, "value": value})


async def api_users(request: web.Request):
    _user, chats = await require_admin(request)
    chat_id = _requested_chat(request, chats)

    query = request.query.get("q", "").strip()[:60]

    people = await list_members(chat_id, query=query, limit=60)

    blocked = await get_blocked_ids(chat_id) if chat_id else set()

    for person in people:
        person["blocked"] = person["telegram_id"] in blocked

    return web.json_response({"users": people})


async def api_user(request: web.Request):
    _user, _chats = await require_admin(request)

    raw = request.query.get("user_id", "")

    if not raw.lstrip("-").isdigit():
        raise web.HTTPBadRequest(text="bad user_id")

    card = await get_user_card(int(raw))

    if card is None:
        raise web.HTTPNotFound(text="user not found")

    return web.json_response(card)


async def api_user_action(request: web.Request):
    """
    Изменить баланс, опыт или заблокировать.
    """
    admin, chats = await require_admin(request)

    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text="bad json")

    action = body.get("action")

    try:
        target = int(body.get("user_id"))
    except (TypeError, ValueError):
        raise web.HTTPBadRequest(text="bad user_id")

    chat_id = body.get("chat_id")

    if chat_id is not None:
        try:
            chat_id = int(chat_id)
        except (TypeError, ValueError):
            raise web.HTTPBadRequest(text="bad chat_id")

        if chat_id not in {chat["chat_id"] for chat in chats}:
            raise web.HTTPForbidden(text="no access to this chat")

    if action in ("coins", "xp"):
        try:
            amount = int(body.get("amount"))
        except (TypeError, ValueError):
            raise web.HTTPBadRequest(text="bad amount")

        if abs(amount) > 1_000_000:
            raise web.HTTPBadRequest(text="too much")

        if action == "coins":
            ok, balance = await change_balance(
                telegram_id=target,
                amount=amount,
                reason="admin",
                note=f"Начисление от админа {admin['id']}",
                chat_id=chat_id,
                allow_negative=False,
            )

            if not ok:
                raise web.HTTPBadRequest(text="not enough coins")

            return web.json_response({"ok": True, "balance": balance})

        result = await award_xp(telegram_id=target, amount=amount)

        return web.json_response({"ok": True, "xp": result.get("xp", 0)})

    if action == "achievement":
        key = body.get("key")

        from progress.achievements import ACHIEVEMENT_BY_KEY

        item = ACHIEVEMENT_BY_KEY.get(key)

        if item is None:
            raise web.HTTPBadRequest(text="unknown achievement")

        granted = await unlock_achievement(target, key)

        if granted and item.reward:
            await change_balance(
                telegram_id=target,
                amount=item.reward,
                reason="achievement",
                note=f"Выдано админом: {item.title}",
                chat_id=chat_id,
            )

        return web.json_response({"ok": True, "granted": granted})

    if action in ("block", "unblock"):
        if chat_id is None:
            raise web.HTTPBadRequest(text="chat_id required")

        if action == "block":
            await block_user(chat_id, target, reason=f"admin {admin['id']}")
            store.set_blocked(chat_id, target, True)
        else:
            await unblock_user(chat_id, target)
            store.set_blocked(chat_id, target, False)

        return web.json_response({"ok": True})

    raise web.HTTPBadRequest(text="unknown action")


# ---------------------------------------------------------
# Достижения, магазин, экономика
# ---------------------------------------------------------

async def api_achievements(request: web.Request):
    await require_admin(request)

    stats = await achievements_stats()

    return web.json_response({
        "items": [
            {
                "key": item.key,
                "emoji": item.emoji,
                "title": item.title,
                "description": item.description,
                "reward": item.reward,
                "secret": item.secret,
                "unlocked": stats.get(item.key, 0),
            }
            for item in ACHIEVEMENTS
        ]
    })


async def api_shop(request: web.Request):
    await require_admin(request)

    stats = await shop_stats()

    categories = []

    for key, (emoji, title) in CATEGORIES.items():
        items = [
            {
                "key": item.key,
                "emoji": item.emoji,
                "title": item.title,
                "price": item.price,
                "description": item.description,
                "owned": stats.get(item.key, {}).get("total", 0),
                "gifted": stats.get(item.key, {}).get("gifted", 0),
            }
            for item in ITEMS
            if item.category == key
        ]

        categories.append({
            "key": key,
            "title": f"{emoji} {title}",
            "items": sorted(items, key=lambda row: row["price"]),
        })

    return web.json_response({"categories": categories})


async def api_economy(request: web.Request):
    _user, chats = await require_admin(request)
    chat_id = _requested_chat(request, chats)

    return web.json_response({
        "totals": await get_overview(chat_id),
        "rich": await top_by("coins", chat_id),
        "history": await recent_transactions(chat_id, limit=30),
    })


# ---------------------------------------------------------
# Статистика, игры, каталог, медиа
# ---------------------------------------------------------

async def api_stats(request: web.Request):
    _user, chats = await require_admin(request)
    chat_id = _requested_chat(request, chats)

    days = request.query.get("days", "30")
    days = int(days) if days.isdigit() and 1 <= int(days) <= 90 else 30

    return web.json_response({
        "series": await get_daily_series(chat_id, days),
        "games": await game_stats(chat_id, days),
        "tops": {
            "messages": await top_by("messages_count", chat_id),
            "xp": await top_by("xp", chat_id),
            "karma": await top_by("karma", chat_id),
            "wins": await top_by("games_won", chat_id),
        },
    })


async def api_catalog(request: web.Request):
    """
    Каталог действий — только просмотр: он живёт в коде.
    """
    await require_admin(request)

    phrase_count = {}

    for category, phrases in CATEGORY_PHRASES.items():
        phrase_count[category] = len(phrases)

    images = {row["collection"]: row for row in await media_stats(limit=400)}

    def images_for(key: str) -> int:
        return sum(
            row["total"]
            for name, row in images.items()
            if name.split("/", 1)[-1].split("#")[0].split(":")[0] == key
        )

    items = []

    for action in ACTIONS:
        if action.category == "pair":
            phrases = len(PAIR.get(action.key, ()))
        elif action.category == "call":
            phrases = len(CALLS.get(action.key, ()))
        else:
            phrases = phrase_count.get(action.category, 0)

        items.append({
            "key": action.key,
            "emoji": action.emoji,
            "title": action.item_acc or action.key,
            "category": action.category,
            "aliases": list(action.aliases),
            "tags": list(action.tags),
            "phrases": phrases,
            "images": images_for(action.key),
        })

    return web.json_response({
        "items": items,
        "categories": sorted({action.category for action in ACTIONS}),
    })


async def api_media(request: web.Request):
    await require_admin(request)

    return web.json_response({"collections": await media_stats()})


# ---------------------------------------------------------
# Логи и система
# ---------------------------------------------------------

async def api_logs(request: web.Request):
    await require_admin(request)

    level = request.query.get("level", "").upper()

    if level not in ("", "INFO", "WARNING", "ERROR", "CRITICAL"):
        level = ""

    return web.json_response({
        "records": logging_setup.ring.tail(limit=120, level=level)
    })


async def api_system(request: web.Request):
    user, chats = await require_admin(request)

    from actions.providers import available_providers
    from games.crocodile import drawing_enabled

    started = request.app.get("started_at", time.time())

    return web.json_response({
        "uptime": int(time.time() - started),
        "providers": available_providers(),
        "drawing": drawing_enabled(),
        "counts": await system_counts(),
        "your_chats": len(chats),
        "owner": is_owner(user["id"]),
    })


# ---------------------------------------------------------
# Рассылка
# ---------------------------------------------------------

async def api_broadcast(request: web.Request):
    user, chats = await require_admin(request)

    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text="bad json")

    text = (body.get("text") or "").strip()

    if not text or len(text) > 3000:
        raise web.HTTPBadRequest(text="bad text")

    raw_chat = body.get("chat_id")
    targets = []

    if raw_chat in (None, "", "all"):
        targets = [chat["chat_id"] for chat in chats]
    else:
        try:
            chat_id = int(raw_chat)
        except (TypeError, ValueError):
            raise web.HTTPBadRequest(text="bad chat_id")

        if chat_id not in {chat["chat_id"] for chat in chats}:
            raise web.HTTPForbidden(text="no access to this chat")

        targets = [chat_id]

    bot = request.app["bot"]
    sent = 0
    failed = 0

    for chat_id in targets:
        try:
            await bot.send_message(chat_id, text)
            sent += 1
        except Exception as error:
            failed += 1
            logger.warning("BROADCAST %s: %s", chat_id, error)

    logger.info("Рассылка от %s: %s из %s", user["id"], sent, len(targets))

    return web.json_response({"ok": True, "sent": sent, "failed": failed})


def setup_admin_routes(app: web.Application) -> None:
    app.router.add_get("/api/admin/session", api_session)
    app.router.add_get("/api/admin/overview", api_overview)
    app.router.add_get("/api/admin/settings", api_settings)
    app.router.add_post("/api/admin/settings", api_set_setting)
    app.router.add_get("/api/admin/users", api_users)
    app.router.add_get("/api/admin/user", api_user)
    app.router.add_post("/api/admin/user", api_user_action)
    app.router.add_get("/api/admin/achievements", api_achievements)
    app.router.add_get("/api/admin/shop", api_shop)
    app.router.add_get("/api/admin/economy", api_economy)
    app.router.add_get("/api/admin/stats", api_stats)
    app.router.add_get("/api/admin/catalog", api_catalog)
    app.router.add_get("/api/admin/media", api_media)
    app.router.add_get("/api/admin/logs", api_logs)
    app.router.add_get("/api/admin/system", api_system)
    app.router.add_post("/api/admin/broadcast", api_broadcast)
