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
from webapp.admin_store import (
    ROLE_PERMISSIONS,
    audit,
    audit_list,
    get_role,
    set_role,
    list_roles,
    get_rules,
    set_rules,
    set_action_override,
    action_override,
    action_overrides,
    sync_gifts,
    gifts_list,
    set_gift_price,
    create_gift_tx,
    update_gift_tx,
    gift_transactions,
    broadcast_history,
    save_broadcast,
)
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


async def _role_for(user_id: int, chat_id: int | None) -> str:
    if is_owner(user_id):
        return "owner"
    if chat_id is None:
        return "moderator"
    return (await get_role(chat_id, user_id)) or "moderator"


async def require_permission(request: web.Request, permission: str, chat_id: int | None = None):
    user, chats = await require_admin(request)
    if chat_id is not None and chat_id not in {c["chat_id"] for c in chats}:
        raise web.HTTPForbidden(text="no access to this chat")
    role = await _role_for(user["id"], chat_id)
    if "*" not in ROLE_PERMISSIONS.get(role, set()) and permission not in ROLE_PERMISSIONS.get(role, set()):
        raise web.HTTPForbidden(text="insufficient role")
    return user, chats, role


async def _target_in_chat(chat_id: int, telegram_id: int) -> bool:
    from database.database import session_scope
    from sqlalchemy import text
    async with session_scope() as session:
        found = await session.scalar(text(
            "SELECT 1 FROM group_members WHERE chat_id=:chat AND telegram_id=:user LIMIT 1"
        ), {"chat": chat_id, "user": telegram_id})
    return bool(found)


# ---------------------------------------------------------
# Эндпоинты
# ---------------------------------------------------------

async def api_session(request: web.Request):
    user, chats = await require_admin(request)

    import changelog

    return web.json_response({
        "version": changelog.latest().version,
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
    role = await _role_for(_user["id"], chat_id)
    if "*" not in ROLE_PERMISSIONS.get(role, set()):
        raise web.HTTPForbidden(text="only owner or super admin can change settings")

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

    await audit(_user["id"], "setting_change", "settings", chat_id=chat_id, details={"key": key, "value": value})
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
    user, chats = await require_admin(request)

    raw = request.query.get("user_id", "")

    if not raw.lstrip("-").isdigit():
        raise web.HTTPBadRequest(text="bad user_id")

    target_id = int(raw)
    raw_chat = request.query.get("chat_id", "").strip()
    chat_id = None
    if raw_chat:
        try:
            chat_id = int(raw_chat)
        except ValueError:
            raise web.HTTPBadRequest(text="bad chat_id")
        if chat_id not in {chat["chat_id"] for chat in chats}:
            raise web.HTTPForbidden(text="no access to this chat")
    elif not is_owner(user["id"]):
        raise web.HTTPBadRequest(text="chat_id required")

    if chat_id is not None and not await _target_in_chat(chat_id, target_id):
        raise web.HTTPNotFound(text="user is not a member of this chat")

    card = await get_user_card(target_id)

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

    if action in ("coins", "xp", "achievement"):
        role = await _role_for(admin["id"], chat_id)
        if "*" not in ROLE_PERMISSIONS.get(role, set()) and "economy" not in ROLE_PERMISSIONS.get(role, set()):
            raise web.HTTPForbidden(text="economy permission required")
    if action in ("block", "unblock"):
        role = await _role_for(admin["id"], chat_id)
        if "*" not in ROLE_PERMISSIONS.get(role, set()) and "moderation" not in ROLE_PERMISSIONS.get(role, set()):
            raise web.HTTPForbidden(text="moderation permission required")

    if not is_owner(admin["id"]):
        if chat_id is None:
            raise web.HTTPBadRequest(text="chat_id required")
        if not await _target_in_chat(chat_id, target):
            raise web.HTTPNotFound(text="user is not a member of this chat")

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
            await audit(admin["id"], "balance_change", "economy", chat_id=chat_id, target_user_id=target, details={"amount": amount, "balance": balance})
            return web.json_response({"ok": True, "balance": balance})

        result = await award_xp(telegram_id=target, amount=amount)
        await audit(admin["id"], "xp_change", "economy", chat_id=chat_id, target_user_id=target, details={"amount": amount, "xp": result.get("xp", 0)})
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
    """Каталог действий + per-group runtime overrides."""
    _user, chats = await require_admin(request)
    chat_id = _requested_chat(request, chats)
    overrides = await action_overrides(chat_id) if chat_id is not None else {}

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
            "enabled": overrides.get(action.key, {}).get("enabled", True),
            "cooldown_seconds": overrides.get(action.key, {}).get("cooldown_seconds", 0),
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

async def require_owner(request: web.Request):
    """
    Логи и система показывают внутренности бота целиком —
    это только для создателя, не для админов отдельных групп.
    """
    user, chats = await require_admin(request)

    if not is_owner(user["id"]):
        raise web.HTTPForbidden(text="owner only")

    return user, chats


async def api_logs(request: web.Request):
    await require_owner(request)

    level = request.query.get("level", "").upper()

    if level not in ("", "INFO", "WARNING", "ERROR", "CRITICAL"):
        level = ""

    return web.json_response({
        "records": logging_setup.ring.tail(limit=120, level=level)
    })


async def api_system(request: web.Request):
    user, chats = await require_owner(request)

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
    await save_broadcast(user["id"], None if len(targets) != 1 else targets[0], text, sent, failed)
    await audit(user["id"], "broadcast", "broadcast", chat_id=None if len(targets) != 1 else targets[0], details={"sent": sent, "failed": failed})

    return web.json_response({"ok": True, "sent": sent, "failed": failed})


# ---------------------------------------------------------
# Аватарки
# ---------------------------------------------------------
#
# Фото людей и групп Telegram отдаёт только боту, по file_id.
# Браузер напрямую их не получит, поэтому сервер скачивает и
# отдаёт сам. Кэш на час, плюс отдельный кэш «фото нет», чтобы
# не дёргать Telegram по людям без аватарки на каждом открытии.
#
# ---------------------------------------------------------

AVATAR_TTL = 3600

_avatar_cache: dict[str, tuple[float, bytes | None]] = {}


async def _download_file(bot, file_id: str) -> bytes | None:
    try:
        telegram_file = await bot.get_file(file_id)
        buffer = await bot.download_file(telegram_file.file_path)
        return buffer.read() if buffer else None
    except Exception as error:
        logger.warning("AVATAR DOWNLOAD: %s", error)
        return None


MISSING_TTL = 300

async def _cached(key: str, loader) -> bytes | None:
    cached = _avatar_cache.get(key)

    if cached:
        age = time.monotonic() - cached[0]
        ttl = AVATAR_TTL if cached[1] else MISSING_TTL

        if age < ttl:
            return cached[1]

    content = await loader()

    _avatar_cache[key] = (time.monotonic(), content)

    # Держим кэш в разумных пределах
    if len(_avatar_cache) > 2000:
        oldest = sorted(_avatar_cache.items(), key=lambda item: item[1][0])

        for stale_key, _value in oldest[:500]:
            _avatar_cache.pop(stale_key, None)

    return content


async def api_avatar(request: web.Request):
    await require_admin(request)

    raw = request.query.get("user_id", "")

    if not raw.lstrip("-").isdigit():
        raise web.HTTPBadRequest(text="bad user_id")

    user_id = int(raw)
    bot = request.app["bot"]

    async def load():
        try:
            photos = await bot.get_user_profile_photos(user_id, limit=1)
        except Exception as error:
            logger.warning("AVATAR %s: %s", user_id, error)
            return None

        if not photos.photos:
            return None

        # Самый маленький размер — для списка его хватает
        return await _download_file(bot, photos.photos[0][0].file_id)

    content = await _cached(f"user:{user_id}", load)

    if not content:
        raise web.HTTPNotFound(text="no photo")

    return web.Response(
        body=content,
        content_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=3600"},
    )


async def api_bot_photo(request: web.Request):
    """
    Аватарка Мары для шапки панели.
    """
    await require_admin(request)

    bot = request.app["bot"]

    async def load():
        try:
            me = await bot.me()
            photos = await bot.get_user_profile_photos(me.id, limit=1)
        except Exception as error:
            logger.warning("BOT PHOTO: %s", error)
            return None

        if not photos.photos:
            return None

        # Средний размер: в шапке аватарка крупнее, чем в списке
        sizes = photos.photos[0]
        return await _download_file(bot, sizes[min(1, len(sizes) - 1)].file_id)

    content = await _cached("bot", load)

    if not content:
        raise web.HTTPNotFound(text="no photo")

    return web.Response(
        body=content,
        content_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=3600"},
    )


async def api_chat_photo(request: web.Request):
    _user, chats = await require_admin(request)

    chat_id = _requested_chat(request, chats)

    if chat_id is None:
        raise web.HTTPBadRequest(text="chat_id required")

    bot = request.app["bot"]

    async def load():
        try:
            chat = await bot.get_chat(chat_id)
        except Exception:
            return None

        if not chat.photo:
            return None

        return await _download_file(bot, chat.photo.small_file_id)

    content = await _cached(f"chat:{chat_id}", load)

    if not content:
        raise web.HTTPNotFound(text="no photo")

    return web.Response(
        body=content,
        content_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=3600"},
    )


# ---------------------------------------------------------
# Модерация
# ---------------------------------------------------------

async def api_moderate(request: web.Request):
    """
    Мут, размут, бан, разбан и выкинуть — для конкретной группы.
    """
    from features.moderation import (
        ModerationError,
        ban,
        kick,
        mute,
        unban,
        unmute,
    )

    admin, chats = await require_admin(request)

    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text="bad json")

    try:
        chat_id = int(body.get("chat_id"))
        target = int(body.get("user_id"))
    except (TypeError, ValueError):
        raise web.HTTPBadRequest(text="bad ids")

    if chat_id not in {chat["chat_id"] for chat in chats}:
        raise web.HTTPForbidden(text="no access to this chat")
    role = await _role_for(admin["id"], chat_id)
    if "*" not in ROLE_PERMISSIONS.get(role, set()) and "moderation" not in ROLE_PERMISSIONS.get(role, set()):
        raise web.HTTPForbidden(text="moderation permission required")

    if target == admin["id"]:
        return web.json_response(
            {"ok": False, "error": "Себя ограничивать нельзя."},
            status=400,
        )

    action = body.get("action")
    bot = request.app["bot"]

    try:
        if action == "mute":
            try:
                minutes = int(body.get("minutes") or 60)
            except (TypeError, ValueError):
                minutes = 60

            # Не меньше минуты и не больше месяца
            minutes = max(1, min(minutes, 60 * 24 * 30))

            await mute(bot, chat_id, target, minutes)
        elif action == "unmute":
            await unmute(bot, chat_id, target)
        elif action == "ban":
            await ban(bot, chat_id, target)
        elif action == "unban":
            await unban(bot, chat_id, target)
        elif action == "kick":
            await kick(bot, chat_id, target)
        else:
            raise web.HTTPBadRequest(text="unknown action")
    except ModerationError as error:
        return web.json_response(
            {"ok": False, "error": str(error)},
            status=400,
        )

    logger.info(
        "Модерация: %s -> %s в %s (%s)",
        admin["id"], target, chat_id, action,
    )
    await audit(admin["id"], action, "moderation", chat_id=chat_id, target_user_id=target, details={"minutes": body.get("minutes")})

    return web.json_response({"ok": True})


async def api_chat_lock(request: web.Request):
    from features.moderation import (
        ModerationError,
        is_chat_locked,
        set_chat_locked,
    )

    _admin, chats = await require_admin(request)

    if request.method == "GET":
        chat_id = _requested_chat(request, chats)

        if chat_id is None:
            raise web.HTTPBadRequest(text="chat_id required")

        locked = await is_chat_locked(request.app["bot"], chat_id)

        return web.json_response({"locked": locked})

    try:
        body = await request.json()
        chat_id = int(body.get("chat_id"))
    except Exception:
        raise web.HTTPBadRequest(text="bad request")

    if chat_id not in {chat["chat_id"] for chat in chats}:
        raise web.HTTPForbidden(text="no access to this chat")

    locked = bool(body.get("locked"))

    try:
        await set_chat_locked(request.app["bot"], chat_id, locked)
    except ModerationError as error:
        return web.json_response(
            {"ok": False, "error": str(error)},
            status=400,
        )

    return web.json_response({"ok": True, "locked": locked})


# ---------------------------------------------------------
# Обновления
# ---------------------------------------------------------

async def api_changelog(request: web.Request):
    await require_admin(request)

    import changelog

    return web.json_response(changelog.as_dict())



async def api_attention(request: web.Request):
    user, chats = await require_admin(request)
    chat_id = _requested_chat(request, chats)
    events = await audit_list(chat_id=chat_id, limit=100)
    attention = []
    for event in events:
        if event.get("result") == "error":
            attention.append({"severity": "critical", "title": event["action"], "details": event.get("details") or {}})
    blocked = await get_blocked_ids(chat_id) if chat_id else set()
    if blocked:
        attention.append({"severity": "warning", "title": "Заблокированные пользователи", "count": len(blocked)})
    return web.json_response({"items": attention[:20]})


async def api_audit(request: web.Request):
    user, chats = await require_admin(request)
    chat_id = _requested_chat(request, chats)
    target = request.query.get("target_user_id")
    target_id = int(target) if target and target.lstrip("-").isdigit() else None
    category = request.query.get("category") or None
    rows = await audit_list(chat_id=chat_id, category=category, target_user_id=target_id, limit=200)
    return web.json_response({"items": rows})


async def api_roles(request: web.Request):
    user, chats = await require_admin(request)
    chat_id = _requested_chat(request, chats)
    if chat_id is None:
        raise web.HTTPBadRequest(text="chat_id required")
    if request.method == "GET":
        return web.json_response({"items": await list_roles(chat_id)})
    if not is_owner(user["id"]):
        raise web.HTTPForbidden(text="owner only")
    body = await request.json()
    try:
        target = int(body.get("telegram_id"))
    except (TypeError, ValueError):
        raise web.HTTPBadRequest(text="bad telegram_id")
    role = str(body.get("role") or "moderator")
    if role not in ROLE_PERMISSIONS or role == "owner":
        raise web.HTTPBadRequest(text="bad role")
    await set_role(chat_id, target, role)
    await audit(user["id"], "role_change", "admins", chat_id=chat_id, target_user_id=target, details={"role": role})
    return web.json_response({"ok": True})


async def api_rules(request: web.Request):
    user, chats = await require_admin(request)
    chat_id = _requested_chat(request, chats)
    if chat_id is None:
        raise web.HTTPBadRequest(text="chat_id required")
    if request.method == "GET":
        return web.json_response({"config": await get_rules(chat_id)})
    if not is_owner(user["id"]):
        role = await _role_for(user["id"], chat_id)
        if "moderation" not in ROLE_PERMISSIONS.get(role, set()):
            raise web.HTTPForbidden(text="insufficient role")
    body = await request.json()
    config = body.get("config")
    if not isinstance(config, dict):
        raise web.HTTPBadRequest(text="config must be object")
    await set_rules(chat_id, config, user["id"])
    await audit(user["id"], "moderation_rules_change", "moderation", chat_id=chat_id, details=config)
    return web.json_response({"ok": True, "config": config})


async def api_action_override(request: web.Request):
    user, chats = await require_admin(request)
    chat_id = _requested_chat(request, chats)
    if chat_id is None:
        raise web.HTTPBadRequest(text="chat_id required")
    if request.method == "GET":
        key = request.query.get("action_key", "")
        if not key:
            raise web.HTTPBadRequest(text="action_key required")
        return web.json_response({"override": await action_override(chat_id, key)})
    role = await _role_for(user["id"], chat_id)
    if "*" not in ROLE_PERMISSIONS.get(role, set()) and "actions" not in ROLE_PERMISSIONS.get(role, set()):
        raise web.HTTPForbidden(text="insufficient role")
    body = await request.json()
    key = str(body.get("action_key") or "")
    if not key or key not in {a.key for a in ACTIONS}:
        raise web.HTTPBadRequest(text="unknown action")
    enabled = bool(body.get("enabled", True))
    cooldown = int(body.get("cooldown_seconds") or 0)
    aliases = body.get("aliases") if isinstance(body.get("aliases"), list) else []
    await set_action_override(chat_id, key, enabled=enabled, cooldown_seconds=cooldown, aliases=[str(x)[:64] for x in aliases[:20]])
    await audit(user["id"], "action_override", "actions", chat_id=chat_id, details={"action": key, "enabled": enabled, "cooldown": cooldown})
    return web.json_response({"ok": True})


async def api_gifts(request: web.Request):
    user, chats = await require_admin(request)
    chat_id = _requested_chat(request, chats)
    token = request.app["bot_token"]
    if request.method == "GET":
        from webapp.telegram_gifts import star_balance
        try:
            balance = await star_balance(token)
        except Exception as error:
            balance = None
            logger.warning("GIFTS BALANCE: %s", error)
        return web.json_response({"balance": balance, "items": await gifts_list(), "transactions": await gift_transactions()})
    role = await _role_for(user["id"], chat_id)
    if "*" not in ROLE_PERMISSIONS.get(role, set()) and "gifts" not in ROLE_PERMISSIONS.get(role, set()):
        raise web.HTTPForbidden(text="insufficient role")
    body = await request.json()
    operation = body.get("operation", "sync")
    if operation == "sync":
        from webapp.telegram_gifts import available_gifts
        raw = await available_gifts(token)
        items = []
        for gift in raw:
            items.append({
                "id": gift.get("id"),
                "star_count": int(gift.get("star_count", 0)),
                "upgrade_star_count": int(gift.get("upgrade_star_count", 0)),
                "is_premium": bool(gift.get("is_premium", False)),
                "total_count": gift.get("total_count"),
                "remaining_count": gift.get("remaining_count"),
                "personal_total_count": gift.get("personal_total_count"),
                "personal_remaining_count": gift.get("personal_remaining_count"),
                "sticker": gift.get("sticker") or {},
            })
        await sync_gifts(items)
        await audit(user["id"], "gift_catalog_sync", "gifts", chat_id=chat_id, details={"count": len(items)})
        return web.json_response({"ok": True, "count": len(items), "items": await gifts_list()})
    if operation == "price":
        gift_id = str(body.get("gift_id") or "")
        price = int(body.get("internal_price") or 0)
        enabled = body.get("enabled")
        await set_gift_price(gift_id, price, None if enabled is None else bool(enabled))
        await audit(user["id"], "gift_price_change", "gifts", chat_id=chat_id, details={"gift_id": gift_id, "price": price, "enabled": enabled})
        return web.json_response({"ok": True})
    if operation == "send":
        try:
            target = int(body.get("target_user_id"))
        except (TypeError, ValueError):
            raise web.HTTPBadRequest(text="bad target_user_id")
        gift_id = str(body.get("gift_id") or "")
        gift = next((x for x in await gifts_list() if x["gift_id"] == gift_id), None)
        if not gift or not gift["enabled"]:
            raise web.HTTPBadRequest(text="gift unavailable")
        if chat_id is None or not await _target_in_chat(chat_id, target):
            raise web.HTTPBadRequest(text="target must belong to selected group")
        from webapp.telegram_gifts import send_gift
        from database.repository import change_balance
        cost = int(gift["internal_price"])
        if cost <= 0:
            raise web.HTTPBadRequest(text="gift has no internal price")
        ok, balance = await change_balance(target, -cost, reason="telegram_gift", note=f"Gift {gift_id}", chat_id=chat_id, allow_negative=False)
        if not ok:
            raise web.HTTPBadRequest(text="not enough diamonds")
        tx = await create_gift_tx(user["id"], target, gift_id, cost, int(gift["star_count"]), chat_id=chat_id)
        try:
            result = await send_gift(token, user_id=target, gift_id=gift_id, text=str(body.get("text") or "")[:128])
        except Exception as error:
            await change_balance(target, cost, reason="telegram_gift_refund", note=f"Gift refund {gift_id}", chat_id=chat_id)
            await update_gift_tx(tx, "failed", {"error": str(error)[:500]})
            await audit(user["id"], "gift_send", "gifts", chat_id=chat_id, target_user_id=target, details={"gift_id": gift_id, "error": str(error)[:300]}, result="error")
            raise web.HTTPBadGateway(text="Telegram gift failed")
        await update_gift_tx(tx, "sent", result if isinstance(result, dict) else {"result": result})
        await audit(user["id"], "gift_send", "gifts", chat_id=chat_id, target_user_id=target, details={"gift_id": gift_id, "diamond_cost": cost, "star_cost": gift["star_count"]})
        return web.json_response({"ok": True, "balance": balance, "transaction_id": tx})
    raise web.HTTPBadRequest(text="unknown operation")


async def api_analytics(request: web.Request):
    user, chats = await require_admin(request)
    chat_id = _requested_chat(request, chats)
    days_raw = request.query.get("days", "30")
    days = max(1, min(90, int(days_raw) if days_raw.isdigit() else 30))
    overview = await get_overview(chat_id)
    series = await get_daily_series(chat_id, days)
    stats = await get_daily_series(chat_id, days)
    return web.json_response({"overview": overview, "series": series, "days": days, "audit": await audit_list(chat_id=chat_id, limit=50), "stats": stats})


async def api_broadcast_history(request: web.Request):
    await require_admin(request)
    return web.json_response({"items": await broadcast_history()})


async def api_chat_permissions(request: web.Request):
    _user, chats = await require_admin(request)
    chat_id = _requested_chat(request, chats)
    if chat_id is None:
        raise web.HTTPBadRequest(text="chat_id required")
    bot = request.app["bot"]
    me = await bot.get_me()
    member = await bot.get_chat_member(chat_id, me.id)
    rights = {}
    for key in ("can_manage_chat", "can_delete_messages", "can_restrict_members", "can_promote_members", "can_change_info", "can_invite_users", "can_pin_messages", "can_manage_topics", "can_manage_tags"):
        rights[key] = bool(getattr(member, key, False))
    return web.json_response({"rights": rights, "status": member.status})

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
    app.router.add_get("/api/admin/avatar", api_avatar)
    app.router.add_get("/api/admin/chat_photo", api_chat_photo)
    app.router.add_get("/api/admin/bot_photo", api_bot_photo)
    app.router.add_get("/api/admin/changelog", api_changelog)
    app.router.add_post("/api/admin/moderate", api_moderate)
    app.router.add_get("/api/admin/chat_lock", api_chat_lock)
    app.router.add_post("/api/admin/chat_lock", api_chat_lock)
    app.router.add_get("/api/admin/attention", api_attention)
    app.router.add_get("/api/admin/audit", api_audit)
    app.router.add_get("/api/admin/roles", api_roles)
    app.router.add_post("/api/admin/roles", api_roles)
    app.router.add_get("/api/admin/rules", api_rules)
    app.router.add_post("/api/admin/rules", api_rules)
    app.router.add_get("/api/admin/action_override", api_action_override)
    app.router.add_post("/api/admin/action_override", api_action_override)
    app.router.add_get("/api/admin/gifts", api_gifts)
    app.router.add_post("/api/admin/gifts", api_gifts)
    app.router.add_get("/api/admin/analytics", api_analytics)
    app.router.add_get("/api/admin/broadcast_history", api_broadcast_history)
    app.router.add_get("/api/admin/chat_permissions", api_chat_permissions)
