"""
API веб-панели.

Вход — через Telegram: панель открывается как Mini App, и Telegram
сам сообщает, кто пришёл. Пароля нет намеренно: публичная админка
с паролем рано или поздно подбирается, а тут подпись проверяется
ключом бота, и подделать её нельзя.

Права: человек видит только те группы, где он администратор.
Владельцы бота из OWNER_IDS видят все.
"""

import asyncio
import logging
import os
import time

from aiohttp import web

from database.repository import (
    member_chats,
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

import audit

from settings import store
from settings.handler import ADMIN_STATUSES, is_creator, is_owner
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


async def ensure_target_access(
    admin: dict,
    chats: list[dict],
    target: int,
    chat_id: int | None = None,
) -> None:
    """
    Может ли этот админ трогать этого человека.

    Раньше не проверялось: админ группы А передавал Telegram ID
    человека из группы Б и менял ему глобальный баланс. Теперь:

      - владелец бота может всё;
      - остальные — только людей из своих групп;
      - если указана конкретная группа, человек должен быть именно в ней.
    """
    if is_owner(admin["id"]):
        return

    allowed = {chat["chat_id"] for chat in chats}

    if chat_id is not None and chat_id not in allowed:
        raise web.HTTPForbidden(text="no access to this chat")

    where = await member_chats(target)

    if chat_id is not None:
        if chat_id not in where:
            raise web.HTTPForbidden(text="user is not in this chat")
        return

    if not where & allowed:
        raise web.HTTPForbidden(text="user is not in your chats")


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

    import changelog

    return web.json_response({
        "version": changelog.latest().version,
        "user": {
            "id": user["id"],
            "name": user.get("first_name") or user.get("username") or "Админ",
            "username": user.get("username"),
            "photo": user.get("photo_url"),
            "owner": is_owner(user["id"]),
            "creator": is_creator(user["id"]),
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

    from settings.registry import CHOICE_BY_KEY as _C, FEATURE_BY_KEY as _F
    from webapp.admin_v2 import require_perm
    from webapp.roles import SECTION_PERMISSION

    item = _F.get(key) or _C.get(key) or NUMBER_BY_KEY.get(key) or TEXT_BY_KEY.get(key)

    if item is None:
        raise web.HTTPBadRequest(text="unknown key")

    admin, _c, _role = await require_perm(
        request, chat_id, SECTION_PERMISSION.get(item.group, "settings"),
    )

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

        if not isinstance(value, str) or (not value.strip() and not text.allow_empty):
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

    audit.log(
        "settings", "change", chat_id=chat_id,
        actor_kind="admin", actor_id=admin["id"],
        actor_name=admin.get("first_name") or admin.get("username"),
        details=f"{item.title}: {value if not isinstance(value, str) or len(value) < 60 else value[:57] + '…'}",
    )

    return web.json_response({"ok": True, "key": key, "value": value})


_admins_cache: dict[int, tuple[float, set[int]]] = {}


async def chat_admin_ids(bot, chat_ids: list[int]) -> set[int]:
    """Администраторы групп — для фильтра и отметки «админ». Кэш 5 минут."""
    result = set()

    for chat_id in chat_ids[:20]:
        cached = _admins_cache.get(chat_id)

        if cached and time.monotonic() - cached[0] < 300:
            result |= cached[1]
            continue

        try:
            admins = await bot.get_chat_administrators(chat_id)
            ids = {m.user.id for m in admins if not m.user.is_bot}
        except Exception:
            admins = []
            ids = set()

        # Админов Telegram отдаёт всегда — пусть они будут в списке, даже если молчат
        from database.repository import ensure_member

        for m in admins:
            if m.user.is_bot:
                continue
            try:
                await ensure_member(chat_id, m.user.id, m.user.first_name or m.user.username)
            except Exception:
                pass

        _admins_cache[chat_id] = (time.monotonic(), ids)
        result |= ids

    return result


async def api_users(request: web.Request):
    from database.repository import members_page

    _user, chats = await require_admin(request)
    chat_id = _requested_chat(request, chats)
    chat_ids = [chat_id] if chat_id else [c["chat_id"] for c in chats]

    query = request.query.get("q", "").strip()[:60]
    flt = request.query.get("filter", "all")[:20]
    sort = request.query.get("sort", "activity")[:20]

    try:
        offset = max(0, int(request.query.get("offset", "0")))
    except ValueError:
        offset = 0

    admin_ids = await chat_admin_ids(request.app["bot"], chat_ids)

    page = await members_page(chat_ids, query=query, flt=flt, sort=sort,
                              admin_ids=admin_ids, limit=40, offset=offset)

    # Сколько людей в группах на самом деле: ботам Telegram не отдаёт список всех,
    # только число — панель показывает «известно N из M».
    page["chat_total"] = await chat_member_total(request.app["bot"], chat_ids)

    return web.json_response(page)


_count_cache: dict[int, tuple[float, int]] = {}


async def chat_member_total(bot, chat_ids: list[int]) -> int | None:
    total = 0
    for chat_id in chat_ids:
        cached = _count_cache.get(chat_id)
        if cached and time.monotonic() - cached[0] < 300:
            total += cached[1]
            continue
        try:
            count = await bot.get_chat_member_count(chat_id)
        except Exception:
            return None
        _count_cache[chat_id] = (time.monotonic(), count)
        total += count
    return total


async def api_user(request: web.Request):
    admin, chats = await require_admin(request)

    # И /api/admin/user?user_id=…, и /api/admin/users/{id}
    raw = request.match_info.get("id") or request.query.get("user_id", "")

    if not raw.lstrip("-").isdigit():
        raise web.HTTPBadRequest(text="bad user_id")

    target = int(raw)

    await ensure_target_access(admin, chats, target)

    card = await get_user_card(target)

    if card is None:
        raise web.HTTPNotFound(text="user not found")

    from database.repository import member_profile, user_history
    from progress.achievements import ACHIEVEMENT_BY_KEY

    chat_id = _requested_chat(request, chats)
    chat_ids = [chat_id] if chat_id else [c["chat_id"] for c in chats]

    member = await member_profile(target, chat_ids)

    for item in member["achievements"]:
        info = ACHIEVEMENT_BY_KEY.get(item["key"])
        item["title"] = info.title if info else item["key"]
        item["emoji"] = info.emoji if info else "🏆"

    history = await user_history(target, chat_ids)

    for item in history:
        if item["type"] == "achievement":
            info = ACHIEVEMENT_BY_KEY.get(item["action"])
            item["details"] = f"{info.emoji} {info.title}" if info else item["action"]

    status = None

    if chat_id:
        try:
            m = await request.app["bot"].get_chat_member(chat_id, target)
            status = m.status
        except Exception:
            status = None

    from progress.xp import progress as xp_progress

    card["progress"] = xp_progress(card["xp"])
    card["member"] = member
    card["history_all"] = history
    card["status"] = status
    card["admin"] = target in await chat_admin_ids(request.app["bot"], chat_ids)

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
        # И POST /api/admin/user, и POST /api/admin/users/{id}/actions
        target = int(request.match_info.get("id") or body.get("user_id"))
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

    # Баланс и опыт глобальные: не-владелец обязан указать свою группу,
    # и человек должен в ней состоять
    if action in ("coins", "xp", "achievement", "karma", "vip") and not is_owner(admin["id"]):
        if chat_id is None:
            raise web.HTTPBadRequest(text="chat_id required")

    await ensure_target_access(admin, chats, target, chat_id)

    from webapp.admin_v2 import require_perm

    needed = "moderation" if action in ("block", "unblock", "vip") else "economy"
    await require_perm(request, chat_id, needed)

    admin_name = admin.get("first_name") or admin.get("username")

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

            audit.log(
                "economy", "coins", chat_id=chat_id, actor_kind="admin",
                actor_id=admin["id"], actor_name=admin_name,
                target_id=target, details=f"{amount:+d} 💎",
            )

            return web.json_response({"ok": True, "balance": balance})

        result = await award_xp(telegram_id=target, amount=amount)

        audit.log(
            "economy", "xp", chat_id=chat_id, actor_kind="admin",
            actor_id=admin["id"], actor_name=admin_name,
            target_id=target, details=f"{amount:+d} xp",
        )

        return web.json_response({"ok": True, "xp": result.get("xp", 0)})

    if action == "karma":
        from database.repository import add_karma

        try:
            amount = int(body.get("amount"))
        except (TypeError, ValueError):
            raise web.HTTPBadRequest(text="bad amount")

        if abs(amount) > 10_000:
            raise web.HTTPBadRequest(text="too much")

        karma = await add_karma(target, amount)

        audit.log(
            "economy", "karma", chat_id=chat_id, actor_kind="admin",
            actor_id=admin["id"], actor_name=admin_name,
            target_id=target, details=f"{amount:+d} ❤️",
        )

        return web.json_response({"ok": True, "karma": karma})

    if action == "vip":
        from database.repository import set_member_vip

        if chat_id is None:
            raise web.HTTPBadRequest(text="chat_id required")

        vip = bool(body.get("value"))
        await set_member_vip(chat_id, target, vip)

        audit.log(
            "moderation", "vip" if vip else "unvip", chat_id=chat_id,
            actor_kind="admin", actor_id=admin["id"], actor_name=admin_name,
            target_id=target,
        )

        return web.json_response({"ok": True, "vip": vip})

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

        audit.log(
            "moderation", "ignore" if action == "block" else "unignore",
            chat_id=chat_id, actor_kind="admin", actor_id=admin["id"],
            actor_name=admin_name, target_id=target,
        )

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
    from database.repository import shop_purchases
    from economy import shop_rules

    _user, chats = await require_admin(request)
    chat_id = _requested_chat(request, chats)
    chat_ids = [chat_id] if chat_id else [c["chat_id"] for c in chats]

    if chat_id and not shop_rules.is_loaded(chat_id):
        await shop_rules.reload(chat_id)

    stats = await shop_stats()
    categories = []

    for key, (emoji, title) in CATEGORIES.items():
        items = []

        for item in ITEMS:
            if item.category != key:
                continue

            rule = shop_rules.rule(chat_id, item.key)

            items.append({
                "key": item.key,
                "emoji": item.emoji,
                "title": item.title,
                "description": item.description,
                "base_price": item.price,
                "price": shop_rules.price(chat_id, item),
                "custom_price": rule.price is not None,
                "enabled": rule.enabled,
                "stock": rule.stock,
                "giftable": item.giftable,
                "owned": stats.get(item.key, {}).get("total", 0),
                "gifted": stats.get(item.key, {}).get("gifted", 0),
            })

        categories.append({
            "key": key,
            "title": f"{emoji} {title}",
            "items": sorted(items, key=lambda row: row["price"]),
        })

    return web.json_response({
        "categories": categories,
        "purchases": await shop_purchases(chat_ids),
    })


async def api_economy(request: web.Request):
    from database.repository import economy_flow

    _user, chats = await require_admin(request)
    chat_id = _requested_chat(request, chats)
    chat_ids = [chat_id] if chat_id else [c["chat_id"] for c in chats]

    reason = request.query.get("reason", "")[:30]
    history = await recent_transactions(chat_id, limit=80)

    if reason:
        history = [h for h in history if h["reason"] == reason]

    return web.json_response({
        "totals": await get_overview(chat_id),
        "today": await economy_flow(chat_ids, days=1),
        "week": await economy_flow(chat_ids, days=7),
        "rich": await top_by("coins", chat_id),
        "history": history[:40],
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


async def api_restart(request: web.Request):
    await require_owner(request)

    async def _do_restart():
        await asyncio.sleep(0.3)
        os._exit(1)  # exit code 1 → Railway restarts the container

    asyncio.ensure_future(_do_restart())
    return web.json_response({"ok": True})


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

    audit.log(
        "broadcast", "sent", actor_kind="admin", actor_id=user["id"],
        actor_name=user.get("first_name"), details=f"{sent} из {len(targets)}",
    )

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
        tempban,
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

    if target == admin["id"]:
        return web.json_response(
            {"ok": False, "error": "Себя ограничивать нельзя."},
            status=400,
        )

    await ensure_target_access(admin, chats, target, chat_id)

    from webapp.admin_v2 import require_perm
    from webapp.roles import bot_rights

    await require_perm(request, chat_id, "moderation")

    action = body.get("action")
    bot = request.app["bot"]

    # Предупреждение не требует прав бота — это запись в базе,
    # а наказание при лимите само проверит права
    if action == "warn":
        from features.automod import warn
        from database.repository import get_user_card

        card = await get_user_card(target)
        reason = str(body.get("reason") or "предупреждение от админа")[:120]

        result = await warn(
            bot, chat_id, target, (card or {}).get("name") or str(target), reason,
            actor_kind="admin", actor_id=admin["id"],
            actor_name=admin.get("first_name") or admin.get("username"),
        )

        return web.json_response({"ok": True, "result": result})

    rights = await bot_rights(bot, chat_id)

    if not rights["restrict"]:
        return web.json_response(
            {"ok": False, "error": "У Мары нет права ограничивать участников в этой группе."},
            status=400,
        )

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
        elif action == "tempban":
            try:
                minutes = int(body.get("minutes") or 1440)
            except (TypeError, ValueError):
                minutes = 1440
            await tempban(bot, chat_id, target, max(1, min(minutes, 60 * 24 * 365)))
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

    audit.log(
        "moderation", action, chat_id=chat_id, actor_kind="admin",
        actor_id=admin["id"], actor_name=admin.get("first_name") or admin.get("username"),
        target_id=target,
        details=f"{body.get('minutes')} мин" if action == "mute" else None,
    )

    audit.count(chat_id, {"mute": "mutes", "ban": "bans", "tempban": "bans"}.get(action, "") or "none")

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

    from webapp.admin_v2 import require_perm

    admin, _c, _r = await require_perm(request, chat_id, "moderation")

    try:
        await set_chat_locked(request.app["bot"], chat_id, locked)
    except ModerationError as error:
        return web.json_response(
            {"ok": False, "error": str(error)},
            status=400,
        )

    audit.log(
        "moderation", "lock" if locked else "unlock", chat_id=chat_id,
        actor_kind="admin", actor_id=admin["id"],
        actor_name=admin.get("first_name") or admin.get("username"),
    )

    return web.json_response({"ok": True, "locked": locked})


# ---------------------------------------------------------
# Обновления
# ---------------------------------------------------------

async def api_changelog(request: web.Request):
    await require_admin(request)

    import changelog

    return web.json_response(changelog.as_dict())


def setup_admin_routes(app: web.Application) -> None:
    app.router.add_get("/api/admin/session", api_session)
    app.router.add_get("/api/admin/overview", api_overview)
    app.router.add_get("/api/admin/settings", api_settings)
    app.router.add_post("/api/admin/settings", api_set_setting)
    app.router.add_get("/api/admin/users", api_users)
    app.router.add_get("/api/admin/user", api_user)
    app.router.add_post("/api/admin/user", api_user_action)

    # Адреса по схеме концепции — синонимы, старые тоже работают
    app.router.add_get("/api/admin/users/{id}", api_user)
    app.router.add_post("/api/admin/users/{id}/actions", api_user_action)
    app.router.add_get("/api/admin/achievements", api_achievements)
    app.router.add_get("/api/admin/shop", api_shop)
    app.router.add_get("/api/admin/economy", api_economy)
    app.router.add_get("/api/admin/stats", api_stats)
    app.router.add_get("/api/admin/catalog", api_catalog)
    app.router.add_get("/api/admin/media", api_media)
    app.router.add_get("/api/admin/logs", api_logs)
    app.router.add_get("/api/admin/system", api_system)
    app.router.add_post("/api/admin/restart", api_restart)
    app.router.add_post("/api/admin/broadcast", api_broadcast)
    app.router.add_get("/api/admin/avatar", api_avatar)
    app.router.add_get("/api/admin/chat_photo", api_chat_photo)
    app.router.add_get("/api/admin/bot_photo", api_bot_photo)
    app.router.add_get("/api/admin/changelog", api_changelog)
    app.router.add_post("/api/admin/moderate", api_moderate)
    app.router.add_get("/api/admin/chat_lock", api_chat_lock)
    app.router.add_post("/api/admin/chat_lock", api_chat_lock)
