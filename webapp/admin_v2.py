"""
API новой админки.

Все изменяющие запросы проверяют ПРАВО роли в конкретной группе,
а не просто «админ ли». Все действия пишутся в журнал.
"""

import base64
import logging
import time
from datetime import datetime, timedelta, timezone

from aiohttp import web

import audit
import logging_setup

from actions.catalog import ACTIONS
from actions.phrases import CALLS, CATEGORY_PHRASES, PAIR

from database.repository import (
    action_file_id,
    action_usage_stats,
    cancel_broadcast,
    change_balance,
    clear_warnings,
    create_broadcast,
    disabled_actions,
    due_broadcasts,
    finish_broadcast,
    get_overview,
    heatmap,
    list_audit,
    list_broadcasts,
    list_roles,
    media_stats,
    recent_violators,
    search_people,
    set_action_enabled,
    set_role,
    today_counters,
    award_xp,
)

from settings import store
from settings.handler import is_owner
from settings.registry import (
    CHOICES,
    FEATURES,
    NUMBERS,
    TEXTS,
    groups as setting_groups,
)

from webapp.roles import (
    ASSIGNABLE,
    PERMISSIONS,
    ROLES,
    bot_rights,
    can,
    forget_role,
    resolve_role,
)


logger = logging.getLogger("maruska.admin")


# ---------------------------------------------------------
# Права
# ---------------------------------------------------------

async def _admin(request):
    from webapp.admin import require_admin

    return await require_admin(request)


def _chat_param(request, chats, required=False):
    raw = request.query.get("chat_id", "").strip()

    if not raw:
        if required:
            raise web.HTTPBadRequest(text="chat_id required")
        return None

    try:
        chat_id = int(raw)
    except ValueError:
        raise web.HTTPBadRequest(text="bad chat_id")

    if chat_id not in {c["chat_id"] for c in chats}:
        raise web.HTTPForbidden(text="no access to this chat")

    return chat_id


async def require_perm(request, chat_id: int | None, permission: str):
    """
    Проверяет право роли. Без группы — достаточно права хотя бы
    в одной из доступных групп (для обзорных экранов).
    """
    admin, chats = await _admin(request)
    bot = request.app["bot"]

    if is_owner(admin["id"]):
        return admin, chats, "owner"

    if chat_id is not None:
        role = await resolve_role(bot, chat_id, admin["id"])

        if not can(role, permission):
            raise web.HTTPForbidden(text=f"no permission: {permission}")

        return admin, chats, role

    for chat in chats:
        role = await resolve_role(bot, chat["chat_id"], admin["id"])

        if can(role, permission):
            return admin, chats, role

    raise web.HTTPForbidden(text=f"no permission: {permission}")


def _name(admin: dict) -> str:
    return admin.get("first_name") or admin.get("username") or str(admin["id"])


# ---------------------------------------------------------
# Кто я в этой группе
# ---------------------------------------------------------

async def api_me(request):
    admin, chats = await _admin(request)
    chat_id = _chat_param(request, chats)
    bot = request.app["bot"]

    role = "owner" if is_owner(admin["id"]) else None
    rights = None

    if chat_id is not None:
        role = await resolve_role(bot, chat_id, admin["id"])
        rights = await bot_rights(bot, chat_id)

    perms = sorted(PERMISSIONS.get(role or "", set()))

    return web.json_response({
        "role": role,
        "role_title": ROLES.get(role or "", ("", "—", ""))[1],
        "permissions": perms,
        "bot_rights": rights,
    })


# ---------------------------------------------------------
# Главная: командный центр
# ---------------------------------------------------------

# ---------------------------------------------------------
# Состояние систем и разбор ошибок
# ---------------------------------------------------------

ERROR_SOURCES = {
    "ai": ("🤖", "AI (Gemini)"),
    "images": ("🖼", "Источники картинок"),
    "telegram": ("✈️", "Telegram API"),
    "database": ("🗄", "База данных"),
    "other": ("⚠️", "Прочее"),
}


def classify_error(record: dict) -> str:
    """К какой системе относится ошибка из лога."""
    text = (record.get("message") or "").upper()
    source = (record.get("logger") or "").lower()

    if "GEMINI" in text or "gemini" in source or "genai" in source:
        return "ai"
    if "maruska.images" in source or any(w in text for w in ("IMAGE", "PIXABAY", "UNSPLASH", "PHOTO", "PROVIDER")):
        return "images"
    if source.startswith("aiogram") or "TELEGRAM" in text:
        return "telegram"
    if any(w in text for w in ("ASYNCPG", "SQLALCHEMY", "DATABASE", "PERSIST", "CONNECTION")) or "database" in source:
        return "database"
    return "other"


def recent_errors(seconds: int = 3600) -> dict:
    """Ошибки за период по источникам: {источник: (сколько, время последней)}."""
    now = time.time()
    result: dict[str, list] = {}

    for record in logging_setup.ring.tail(limit=300, level="ERROR"):
        if now - record["time"] > seconds:
            continue

        item = result.setdefault(classify_error(record), [0, 0.0])
        item[0] += 1
        item[1] = max(item[1], record["time"])

    return {k: (v[0], v[1]) for k, v in result.items()}


_status_cache: dict = {"at": 0.0, "value": None}


async def system_status(bot) -> dict:
    """
    Реальные проверки, а не заглушки: база отвечает на запрос,
    Telegram отвечает на getMe, у AI есть ключ и нет свежих ошибок.
    Кэш 30 секунд — главную открывают часто.
    """
    import asyncio
    import os

    if _status_cache["value"] and time.monotonic() - _status_cache["at"] < 30:
        return _status_cache["value"]

    async def timed(coro):
        start = time.monotonic()
        try:
            await asyncio.wait_for(coro, timeout=5)
            return {"ok": True, "ms": int((time.monotonic() - start) * 1000)}
        except Exception as error:
            return {"ok": False, "error": type(error).__name__}

    async def db_ping():
        from sqlalchemy import text
        from database.database import session_scope

        async with session_scope() as session:
            await session.execute(text("SELECT 1"))

    from actions.providers import available_providers

    errors = recent_errors(1800)

    ai_key = bool(os.getenv("GEMINI_API_KEY"))
    ai_errors = errors.get("ai", (0, 0))[0]

    # Своя коллекция — тоже источник картинок: без Pixabay бот работает на ней
    try:
        from database.repository import library_summary

        library_ok = any(int(row.get("count") or 0) for row in await library_summary())
    except Exception:
        library_ok = False

    status = {
        "database": await timed(db_ping()),
        "telegram": await timed(bot.get_me()),
        "ai": {"ok": ai_key and not ai_errors, "configured": ai_key, "errors": ai_errors},
        "images": {"ok": (bool(available_providers()) or library_ok) and not errors.get("images", (0, 0))[0],
                   "configured": bool(available_providers()) or library_ok, "errors": errors.get("images", (0, 0))[0]},
        "actions": {"ok": len(ACTIONS) > 0, "count": len(ACTIONS)},
    }

    status["online"] = status["telegram"]["ok"]
    status["all_ok"] = all(v["ok"] for k, v in status.items() if isinstance(v, dict))

    _status_cache.update(at=time.monotonic(), value=status)

    return status


async def build_attention(bot, chat_id, chats, owner: bool) -> list[dict]:
    items = []
    ids = [chat_id] if chat_id else [c["chat_id"] for c in chats]

    violators = await recent_violators(chat_id, ids, limit=5)

    if violators:
        items.append({
            "level": "warn",
            "icon": "⚠️",
            "text": f"{len(violators)} нарушителей за неделю",
            "object": "Модерация",
            "go": "moderation",
        })

    today = await today_counters(chat_id, ids)

    if today["new_users"]:
        items.append({
            "level": "info",
            "icon": "👋",
            "text": f"{today['new_users']} новых участников сегодня",
            "object": "Участники",
            "go": "users",
        })

    for cid in ids[:10]:
        rights = await bot_rights(bot, cid)

        if not rights["admin"] or not rights["restrict"]:
            title = next((c["title"] for c in chats if c["chat_id"] == cid), cid)
            items.append({
                "level": "warn",
                "icon": "🔑",
                "text": f"У Мары нет прав модерации в «{title}»",
                "object": f"Группа «{title}»",
                "go": "groups",
            })

    if owner:
        for source, (count, last) in sorted(recent_errors(3600).items(), key=lambda kv: -kv[1][0]):
            icon, title = ERROR_SOURCES.get(source, ERROR_SOURCES["other"])
            items.append({
                "level": "danger" if source in ("database", "telegram", "ai") else "warn",
                "icon": icon,
                "text": f"{title}: {count} ошибок за час",
                "object": title,
                "at": datetime.fromtimestamp(last, timezone.utc).replace(tzinfo=None).isoformat(),
                "go": "logs",
            })

        from actions.providers import available_providers
        from database.repository import library_summary

        library_has_images = any(int(row.get("count") or 0) for row in await library_summary())

        # Тревога, только если картинок нет совсем: ни внешних источников,
        # ни своей коллекции. Работа только на своей коллекции — норма.
        if not available_providers() and not library_has_images:
            items.append({
                "level": "danger",
                "icon": "🖼",
                "text": "Не настроен ни один источник картинок",
                "go": "system",
            })

    return items


async def api_dashboard(request):
    admin, chats = await _admin(request)
    chat_id = _chat_param(request, chats)
    bot = request.app["bot"]
    owner = is_owner(admin["id"])

    ids = [chat_id] if chat_id else [c["chat_id"] for c in chats]

    status = await system_status(bot)
    status["uptime"] = int(time.time() - request.app.get("started_at", time.time()))

    return web.json_response({
        "status": status,
        "totals": await get_overview(chat_id),
        "today": await today_counters(chat_id, ids),
        "attention": await build_attention(bot, chat_id, chats, owner),
        "events": await list_audit(ids if not owner or chat_id else None, limit=8),
    })


# ---------------------------------------------------------
# Журнал
# ---------------------------------------------------------

async def api_journal(request):
    from database.repository import audit_actors

    admin, chats = await require_perm(request, None, "journal")
    chat_id = _chat_param(request, chats)

    ids = [chat_id] if chat_id else [c["chat_id"] for c in chats]
    scope = None if (is_owner(admin["id"]) and not chat_id) else ids

    def as_int(name):
        raw = request.query.get(name, "")
        return int(raw) if raw.lstrip("-").isdigit() else None

    def as_date(name, shift=0):
        raw = request.query.get(name, "")
        try:
            return datetime.strptime(raw, "%Y-%m-%d") + timedelta(days=shift) if raw else None
        except ValueError:
            raise web.HTTPBadRequest(text=f"bad {name}")

    kind = request.query.get("actor_kind", "")

    return web.json_response({
        "events": await list_audit(
            scope,
            category=request.query.get("category", "")[:20],
            query=request.query.get("q", "").strip()[:60],
            target_id=as_int("user_id"),
            actor_id=as_int("actor_id"),
            actor_kind=kind if kind in ("admin", "bot", "system") else "",
            date_from=as_date("from"),
            date_to=as_date("to", shift=1),
            limit=150,
        ),
        "actors": await audit_actors(scope),
    })


# ---------------------------------------------------------
# Модерация: нарушители
# ---------------------------------------------------------

async def api_violators(request):
    admin, chats = await _admin(request)
    chat_id = _chat_param(request, chats)
    ids = [chat_id] if chat_id else [c["chat_id"] for c in chats]

    return web.json_response({
        "violators": await recent_violators(chat_id, ids, limit=20),
    })


async def api_clear_warnings(request):
    body = await request.json()
    chat_id = int(body.get("chat_id"))
    target = int(body.get("user_id"))

    admin, _chats, _role = await require_perm(request, chat_id, "moderation")

    await clear_warnings(chat_id, target)

    audit.log(
        "moderation", "clear_warnings", chat_id=chat_id,
        actor_kind="admin", actor_id=admin["id"], actor_name=_name(admin),
        target_id=target,
    )

    return web.json_response({"ok": True})


# ---------------------------------------------------------
# Роли
# ---------------------------------------------------------

async def api_roles(request):
    bot = request.app["bot"]

    if request.method == "GET":
        admin, chats = await _admin(request)
        chat_id = _chat_param(request, chats, required=True)

        await require_perm(request, chat_id, "view")

        assigned = await list_roles(chat_id)
        people = []

        try:
            admins = await bot.get_chat_administrators(chat_id)
        except Exception:
            admins = []

        for member in admins:
            if member.user.is_bot:
                continue

            uid = member.user.id
            role = await resolve_role(bot, chat_id, uid)

            people.append({
                "telegram_id": uid,
                "name": member.user.first_name or member.user.username or str(uid),
                "status": member.status,
                "role": role,
                "explicit": uid in assigned,
            })

        return web.json_response({
            "admins": people,
            "roles": [
                {"key": key, "emoji": ROLES[key][0], "title": ROLES[key][1], "hint": ROLES[key][2]}
                for key in ASSIGNABLE
            ],
        })

    body = await request.json()
    chat_id = int(body.get("chat_id"))
    target = int(body.get("user_id"))
    role = body.get("role") or None

    admin, _chats, _r = await require_perm(request, chat_id, "roles")

    if role is not None and role not in ASSIGNABLE:
        raise web.HTTPBadRequest(text="bad role")

    await set_role(chat_id, target, role)
    forget_role(chat_id, target)

    audit.log(
        "settings", "role", chat_id=chat_id,
        actor_kind="admin", actor_id=admin["id"], actor_name=_name(admin),
        target_id=target, details=ROLES.get(role or "", ("", "по правам Telegram", ""))[1],
    )

    return web.json_response({"ok": True})


# ---------------------------------------------------------
# Действия
# ---------------------------------------------------------

# Жесты в каталоге — одна категория «pair». Для фильтров панели
# раскладываем их по темам из концепции.
PAIR_THEMES = {
    "relations": ("hug", "kiss", "carry", "pat", "tickle", "wake", "lull", "cover", "walk_home"),
    "emotions": ("praise", "scold", "support", "congratulations", "wink", "sing"),
    "greetings": ("highfive", "handshake"),
    "leisure": ("party", "movie", "music", "dance", "banya", "fishing", "gym", "game",
                "selfie", "sea", "walk", "coffee_break", "photo"),
}

THEME_BY_KEY = {key: theme for theme, keys in PAIR_THEMES.items() for key in keys}


def action_theme(action) -> str:
    if action.category == "pair":
        return THEME_BY_KEY.get(action.key, "relations")
    if action.category == "call":
        return "humor"
    return action.category


def _phrases(action) -> int:
    if action.category == "pair":
        return len(PAIR.get(action.key, ()))
    if action.category == "call":
        return len(CALLS.get(action.key, ()))
    return len(CATEGORY_PHRASES.get(action.category, ()))


async def api_actions(request):
    admin, chats = await _admin(request)
    chat_id = _chat_param(request, chats)

    from actions import custom as ac

    usage = await action_usage_stats(chat_id, days=7)
    disabled = await disabled_actions(chat_id) if chat_id else set()

    if chat_id and not ac.is_loaded(chat_id):
        await ac.reload(chat_id)

    own = ac.get(chat_id)
    own_count = {}

    for alias_key in own.aliases.values():
        own_count[alias_key] = own_count.get(alias_key, 0) + 1

    for key_, items in list(own.phrases.items()) + list(own.images.items()):
        own_count[key_] = own_count.get(key_, 0) + len(items)

    images = {}

    for row in await media_stats(limit=500):
        key = row["collection"].split("/", 1)[-1].split("#")[0].split(":")[0]
        images[key] = images.get(key, 0) + row["total"]

    return web.json_response({
        "actions": [
            {
                "key": a.key,
                "emoji": a.emoji,
                "title": (a.item_acc or a.key).capitalize(),
                "category": a.category,
                "theme": action_theme(a),
                "aliases": list(a.aliases),
                "phrases": _phrases(a),
                "images": images.get(a.key, 0),
                "usage": usage.get(a.key, 0),
                "enabled": a.key not in disabled,
                "custom": own_count.get(a.key, 0),
                "cooldown": own.cooldown.get(a.key, 0),
            }
            for a in ACTIONS
        ]
    })


async def api_action_toggle(request):
    body = await request.json()
    chat_id = int(body.get("chat_id"))
    key = body.get("key")
    enabled = bool(body.get("enabled"))

    admin, _chats, _role = await require_perm(request, chat_id, "content")

    if key not in {a.key for a in ACTIONS}:
        raise web.HTTPBadRequest(text="unknown action")

    await set_action_enabled(chat_id, key, enabled)
    store.set_action_disabled(chat_id, key, not enabled)

    audit.log(
        "actions", "toggle", chat_id=chat_id,
        actor_kind="admin", actor_id=admin["id"], actor_name=_name(admin),
        details=f"{key}: {'включено' if enabled else 'выключено'}",
    )

    return web.json_response({"ok": True})


async def api_action_image(request):
    await _admin(request)

    key = request.query.get("key", "")
    image_id = request.query.get("id", "")

    if image_id.isdigit():
        from database.repository import get_action_image_row

        row = await get_action_image_row(int(image_id))
        file_id = row.telegram_file_id if row else None
        key = f"{key}#{image_id}"
    else:
        file_id = await action_file_id(key)

    if not file_id:
        raise web.HTTPNotFound(text="no image")

    from webapp.admin import _cached, _download_file

    content = await _cached(f"action:{key}", lambda: _download_file(request.app["bot"], file_id))

    if not content:
        raise web.HTTPNotFound(text="no image")

    return web.Response(
        body=content,
        content_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=3600"},
    )


# ---------------------------------------------------------
# Рассылки
# ---------------------------------------------------------

MAX_PHOTO = 5 * 1024 * 1024
MAX_VIDEO = 10 * 1024 * 1024
MEDIA_TYPES = ("photo", "video", "animation")


def _check_media(body) -> tuple[str | None, str]:
    """Проверяет вложение рассылки: data:-загрузка или https-ссылка."""
    media = body.get("photo") or None
    kind = body.get("media_type") if body.get("media_type") in MEDIA_TYPES else "photo"

    if not media:
        return None, kind

    if media.startswith("data:"):
        try:
            raw = base64.b64decode(media.split(",", 1)[1])
        except Exception:
            raise web.HTTPBadRequest(text="bad media")

        limit = MAX_PHOTO if kind == "photo" else MAX_VIDEO

        if len(raw) > limit:
            raise web.HTTPBadRequest(text="media too big")
    elif not media.startswith("https://"):
        raise web.HTTPBadRequest(text="bad media url")

    return media, kind


def _buttons(body) -> list:
    result = []

    for button in (body.get("buttons") or [])[:6]:
        label = str(button.get("text", "")).strip()[:40]
        url = str(button.get("url", "")).strip()[:300]

        if label and url.startswith(("http://", "https://", "tg://")):
            result.append({"text": label, "url": url})

    return result


async def send_broadcast_message(bot, chat_id: int, text: str, media: str | None,
                                 media_type: str, buttons: list):
    """Одна отправка рассылки — общая для цикла и для теста."""
    from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup

    markup = None

    if buttons:
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=b["text"], url=b["url"])] for b in buttons
        ])

    if not media:
        return await bot.send_message(chat_id, text, reply_markup=markup)

    if media.startswith("data:"):
        names = {"photo": "broadcast.jpg", "video": "broadcast.mp4", "animation": "broadcast.gif"}
        file = BufferedInputFile(base64.b64decode(media.split(",", 1)[1]), filename=names[media_type])
    else:
        file = media

    caption = text[:1024]

    if media_type == "video":
        return await bot.send_video(chat_id, file, caption=caption, reply_markup=markup)

    if media_type == "animation":
        return await bot.send_animation(chat_id, file, caption=caption, reply_markup=markup)

    return await bot.send_photo(chat_id, file, caption=caption, reply_markup=markup)


def _segment(body) -> dict:
    from database.repository import SEGMENTS

    raw = body.get("segment") or {}
    kind = raw.get("type") if raw.get("type") in SEGMENTS else "all"
    value = raw.get("value")

    if kind in ("level", "balance"):
        try:
            value = max(0, int(value or 0))
        except (TypeError, ValueError):
            raise web.HTTPBadRequest(text="bad segment value")
    elif kind == "achievement":
        value = str(value or "")[:40]
    else:
        value = None

    return {"type": kind, "value": value}


async def api_broadcast_audience(request):
    """Сколько человек получит личную рассылку — до отправки."""
    from database.repository import dm_audience

    admin, chats, _role = await require_perm(request, None, "broadcast")
    body = await request.json()

    allowed = [c["chat_id"] for c in chats]
    targets = body.get("chat_ids") or "all"
    ids = allowed if targets == "all" else [int(t) for t in targets if int(t) in allowed]

    people = await dm_audience(ids, _segment(body))

    return web.json_response({"ok": True, "count": len(people)})


async def api_broadcast_test(request):
    """Тест себе в личку — до отправки в группы."""
    admin, _chats, _role = await require_perm(request, None, "broadcast")
    body = await request.json()

    text = (body.get("text") or "").strip()

    if not text:
        return web.json_response({"ok": False, "error": "Напиши текст"}, status=400)

    media, kind = _check_media(body)

    try:
        await send_broadcast_message(request.app["bot"], admin["id"], text, media, kind, _buttons(body))
    except Exception as error:
        message = str(error).lower()

        if "chat not found" in message or "bot can't initiate" in message or "forbidden" in message:
            reason = "Сначала напиши Маре в личку /start — иначе она не может тебе писать"
        elif "can't parse" in message:
            reason = "Telegram не понял разметку в тексте — проверь теги <b>, <i>"
        else:
            reason = "Telegram не принял сообщение"

        return web.json_response({"ok": False, "error": reason}, status=400)

    return web.json_response({"ok": True})


async def api_broadcasts(request):
    if request.method == "GET":
        admin, chats = await require_perm(request, None, "broadcast")
        ids = None if is_owner(admin["id"]) else [c["chat_id"] for c in chats]
        return web.json_response({"broadcasts": await list_broadcasts(ids)})

    body = await request.json()
    admin, chats, _role = await require_perm(request, None, "broadcast")

    allowed = {c["chat_id"] for c in chats}
    targets = body.get("chat_ids") or []

    if targets == "all" or not targets:
        targets = list(allowed)

    try:
        targets = [int(t) for t in targets]
    except (TypeError, ValueError):
        raise web.HTTPBadRequest(text="bad chat_ids")

    if not set(targets) <= allowed:
        raise web.HTTPForbidden(text="no access to some chats")

    text = (body.get("text") or "").strip()

    if not text or len(text) > 3500:
        raise web.HTTPBadRequest(text="bad text")

    photo, media_type = _check_media(body)
    buttons = _buttons(body)

    mode = "dm" if body.get("mode") == "dm" else "groups"
    segment = _segment(body) if mode == "dm" else {}

    send_at = datetime.now(timezone.utc).replace(tzinfo=None)

    if body.get("send_at"):
        try:
            parsed = datetime.fromisoformat(str(body["send_at"]).replace("Z", "+00:00"))
            if parsed.tzinfo:
                parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
            send_at = max(send_at, parsed)
        except ValueError:
            raise web.HTTPBadRequest(text="bad send_at")

    broadcast_id = await create_broadcast(
        admin["id"], _name(admin), targets, text, photo, buttons, send_at, media_type,
        mode=mode, segment=segment,
    )

    audit.log(
        "broadcast", "created",
        actor_kind="admin", actor_id=admin["id"], actor_name=_name(admin),
        details=(f"в личку · сегмент {segment.get('type')}" if mode == "dm" else f"{len(targets)} групп")
                + f" · {send_at:%d.%m %H:%M} UTC",
    )

    return web.json_response({"ok": True, "id": broadcast_id})


async def api_broadcast_cancel(request):
    body = await request.json()
    admin, _chats, _role = await require_perm(request, None, "broadcast")

    ok = await cancel_broadcast(
        int(body.get("id")),
        None if is_owner(admin["id"]) else admin["id"],
    )

    return web.json_response({"ok": ok})


async def broadcast_loop(bot):
    """Раз в 20 секунд отправляет рассылки, у которых подошло время."""
    import asyncio

    while True:
        try:
            await asyncio.sleep(20)

            for item in await due_broadcasts():
                sent = failed = 0

                recipients = item.chat_ids or []

                if (item.mode or "groups") == "dm":
                    from database.repository import dm_audience

                    recipients = await dm_audience(item.chat_ids or [], item.segment or {})

                for chat_id in recipients:
                    try:
                        await send_broadcast_message(
                            bot, chat_id, item.text, item.photo,
                            item.media_type or "photo", item.buttons or [],
                        )
                        sent += 1
                    except Exception as error:
                        failed += 1
                        logger.warning("BROADCAST %s → %s: %s", item.id, chat_id, error)

                        # Человек заблокировал бота — больше в личку не пишем
                        if (item.mode or "groups") == "dm" and "forbidden" in str(error).lower():
                            from database.repository import mark_dm_ok

                            await mark_dm_ok(chat_id, False)

                    await asyncio.sleep(0.2)

                await finish_broadcast(item.id, sent, failed)

                audit.log(
                    "broadcast", "sent", actor_kind="system",
                    details=f"#{item.id}: {sent} отправлено, {failed} ошибок",
                )

        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.error("BROADCAST LOOP: %s %s", type(error).__name__, error)


# ---------------------------------------------------------
# Аналитика, уведомления, поиск
# ---------------------------------------------------------

def _tz_info(chat_id):
    """Сдвиг и подпись часового пояса для графиков по часам."""
    if not chat_id:
        return 0, "UTC"
    return store.utc_offset_hours(chat_id), store.get_value(chat_id, "timezone") or "UTC"


async def api_heatmap(request):
    _admin_user, chats = await _admin(request)
    chat_id = _chat_param(request, chats)
    offset, tz = _tz_info(chat_id)

    return web.json_response({"grid": await heatmap(chat_id, days=28, offset=offset), "tz": tz})


async def api_notifications(request):
    admin, chats = await _admin(request)
    chat_id = _chat_param(request, chats)

    return web.json_response({
        "items": await build_attention(
            request.app["bot"], chat_id, chats, is_owner(admin["id"]),
        )
    })


async def api_search(request):
    admin, chats = await _admin(request)
    query = request.query.get("q", "").strip()[:60]

    if len(query) < 2:
        return web.json_response({"people": [], "actions": [], "settings": [], "events": [], "groups": []})

    ids = None if is_owner(admin["id"]) else [c["chat_id"] for c in chats]
    lowered = query.lower()

    actions = [
        {"key": a.key, "emoji": a.emoji, "title": (a.item_acc or a.key).capitalize()}
        for a in ACTIONS
        if lowered in a.key or any(lowered in alias.lstrip("=") for alias in a.aliases)
    ][:8]

    settings = [
        {"key": item.key, "emoji": item.emoji, "title": item.title, "group": item.group}
        for item in list(FEATURES) + list(CHOICES) + list(NUMBERS) + list(TEXTS)
        if lowered in item.title.lower() or lowered in item.description.lower()
    ][:8]

    groups = [
        {"chat_id": c["chat_id"], "title": c["title"], "members": c["members"]}
        for c in chats
        if lowered in (c["title"] or "").lower() or query == str(c["chat_id"])
    ][:6]

    return web.json_response({
        "people": await search_people(query, ids),
        "actions": actions,
        "settings": settings,
        "groups": groups,
        "events": await list_audit(ids, query=query, limit=6),
    })


# ---------------------------------------------------------
# Отмена последнего изменения баланса / опыта
# ---------------------------------------------------------

async def api_undo(request):
    body = await request.json()
    chat_id = int(body.get("chat_id")) if body.get("chat_id") else None

    admin, chats, _role = await require_perm(request, chat_id, "economy")

    from webapp.admin import ensure_target_access

    target = int(body.get("user_id"))
    await ensure_target_access(admin, chats, target, chat_id)

    kind = body.get("kind")
    amount = int(body.get("amount"))

    if kind == "coins":
        ok, balance = await change_balance(
            telegram_id=target, amount=-amount, reason="admin",
            note="Отмена изменения", chat_id=chat_id, allow_negative=False,
        )
        if not ok:
            raise web.HTTPBadRequest(text="cannot undo")
    elif kind == "xp":
        await award_xp(telegram_id=target, amount=-amount)
    elif kind == "karma":
        from database.repository import add_karma

        await add_karma(target, -amount)
    else:
        raise web.HTTPBadRequest(text="bad kind")

    audit.log(
        "economy", "undo", chat_id=chat_id,
        actor_kind="admin", actor_id=admin["id"], actor_name=_name(admin),
        target_id=target, details=f"{kind} {-amount:+d}",
    )

    return web.json_response({"ok": True})


# ---------------------------------------------------------
# Редактор действия
# ---------------------------------------------------------

def _templates_for(action) -> list[str]:
    from actions.phrases import FALLBACK

    if action.category == "pair":
        return list(PAIR.get(action.key, ())) or list(FALLBACK)
    if action.category == "call":
        return list(CALLS.get(action.key, ())) or list(FALLBACK)
    return list(CATEGORY_PHRASES.get(action.category, ())) or list(FALLBACK)


async def _content_perm(request, body):
    try:
        chat_id = int(body.get("chat_id"))
    except (TypeError, ValueError):
        raise web.HTTPBadRequest(text="chat_id required")

    admin, chats, role = await require_perm(request, chat_id, "content")
    return admin, chat_id


def _action_or_404(key):
    from actions.custom import ACTION_BY_KEY

    action = ACTION_BY_KEY.get(key or "")

    if action is None:
        raise web.HTTPNotFound(text="unknown action")

    return action


async def api_action_detail(request):
    from actions import custom as ac
    from database.repository import action_pool_images, list_action_custom

    admin, chats = await _admin(request)
    chat_id = _chat_param(request, chats)
    action = _action_or_404(request.query.get("key"))

    rows = await list_action_custom(chat_id, action.key) if chat_id else []
    usage = (await action_usage_stats(chat_id, days=7)).get(action.key, 0)
    usage_30 = (await action_usage_stats(chat_id, days=30)).get(action.key, 0)
    disabled = action.key in (await disabled_actions(chat_id) if chat_id else set())

    hidden = {int(r.value) for r in rows if r.kind == "hide_image" and r.value.isdigit()}
    hidden_aliases = {r.value for r in rows if r.kind == "hide_alias"}
    # Скрытые фразы — на уровне группы: они общие для категории
    all_rows = await list_action_custom(chat_id) if chat_id else []
    hidden_phrases = {r.value for r in all_rows if r.kind == "hide_phrase"}
    cooldown = next((int(r.value) for r in rows if r.kind == "cooldown" and r.value.isdigit()), 0)
    image_mode = next((r.value for r in rows if r.kind == "image_mode"), "mix")

    pool = await action_pool_images(action.key)

    for image in pool:
        image["hidden"] = image["id"] in hidden

    templates = _templates_for(action)

    return web.json_response({
        "key": action.key,
        "emoji": action.emoji,
        "title": (action.item_acc or action.key).capitalize(),
        "category": action.category,
        "aliases": [a.lstrip("=") for a in action.aliases],
        "builtin_aliases": [
            {"value": a, "text": a.lstrip("="), "hidden": a in hidden_aliases}
            for a in action.aliases
        ],
        "tags": list(action.tags),
        "enabled": not disabled,
        "usage_7": usage,
        "usage_30": usage_30,
        "cooldown": cooldown,
        "image_mode": image_mode,
        "gender_logic": "Глаголы подстраиваются под пол по имени: «угостил» / «угостила»",
        "target_logic": "Срабатывает в ответ на сообщение человека или с @ником",
        "pair_logic": action.category == "pair",
        "builtin_phrases": [
            {
                "template": t,
                "preview": ac.preview_phrase(t, "male", emoji=action.emoji, item=action.item_acc or "", item_instr=action.item_instr or ""),
                "hidden": t in hidden_phrases,
            }
            for t in templates
        ],
        "phrases_shared": action.category not in ("pair", "call"),
        "custom": [
            {"id": r.id, "kind": r.kind, "value": r.value if r.kind != "image" or not r.value.startswith("data:") else "загружено",
             "shows": r.shows, "cached": bool(r.file_id),
             "last_used": r.last_used_at.isoformat() if getattr(r, "last_used_at", None) else None}
            for r in rows if r.kind in ("alias", "phrase", "image")
        ],
        "pool": pool,
        "placeholders": ac.PLACEHOLDERS,
    })


async def api_action_custom(request):
    from actions import custom as ac
    from database.repository import add_action_custom

    body = await request.json()
    admin, chat_id = await _content_perm(request, body)
    action = _action_or_404(body.get("key"))

    kind = body.get("kind")
    value = str(body.get("value") or "").strip()

    if kind == "alias":
        error = ac.validate_alias(value)
        value = ac.normalize_alias(value)

        if not error:
            from actions.catalog import find_action

            clash = find_action(value)

            if clash is not None and clash.key != action.key:
                error = f"Это слово уже запускает «{clash.item_acc or clash.key}»"
            elif value in ac.get(chat_id).aliases and ac.get(chat_id).aliases[value] != action.key:
                error = "Это слово уже занято другим действием в группе"

    elif kind == "phrase":
        error = ac.validate_phrase(value)

    elif kind == "image":
        error = None

        if value.startswith("data:image/"):
            try:
                raw = base64.b64decode(value.split(",", 1)[1])
            except Exception:
                raw = b""

            if not raw:
                error = "Не удалось прочитать картинку"
            elif len(raw) > ac.MAX_UPLOAD:
                error = "Картинка больше 2 МБ"
        elif not value.startswith("https://"):
            error = "Нужна ссылка https://… или загрузка файла"
        else:
            problem = await _check_image_url(value)
            error = problem
    else:
        raise web.HTTPBadRequest(text="bad kind")

    if error:
        return web.json_response({"ok": False, "error": error}, status=400)

    custom_id = await add_action_custom(chat_id, action.key, kind, value, admin["id"])
    await ac.reload(chat_id)

    audit.log(
        "actions", f"add_{kind}", chat_id=chat_id,
        actor_kind="admin", actor_id=admin["id"], actor_name=_name(admin),
        details=f"{action.key}: " + (value[:80] if kind != "image" else "картинка"),
    )

    return web.json_response({"ok": True, "id": custom_id})


async def api_action_custom_delete(request):
    from actions import custom as ac
    from database.repository import delete_action_custom

    body = await request.json()
    admin, chat_id = await _content_perm(request, body)

    info = await delete_action_custom(chat_id, int(body.get("id")))

    if info is None:
        raise web.HTTPNotFound(text="not found")

    await ac.reload(chat_id)

    audit.log(
        "actions", f"remove_{info['kind']}", chat_id=chat_id,
        actor_kind="admin", actor_id=admin["id"], actor_name=_name(admin),
        details=info["action_key"],
    )

    return web.json_response({"ok": True})


async def api_action_option(request):
    from actions import custom as ac
    from database.repository import set_action_custom_single

    body = await request.json()
    admin, chat_id = await _content_perm(request, body)
    action = _action_or_404(body.get("key"))

    kind = body.get("kind")

    if kind == "cooldown":
        try:
            seconds = max(0, min(int(body.get("value")), 3600))
        except (TypeError, ValueError):
            raise web.HTTPBadRequest(text="bad value")
        value = str(seconds) if seconds else None
        label = f"задержка {seconds} сек"
    elif kind == "image_mode":
        value = body.get("value") if body.get("value") in ("mix", "own") else "mix"
        label = "только свои картинки" if value == "own" else "свои вперемешку с общими"
    else:
        raise web.HTTPBadRequest(text="bad kind")

    await set_action_custom_single(chat_id, action.key, kind, value, admin["id"])
    await ac.reload(chat_id)

    audit.log(
        "actions", "option", chat_id=chat_id,
        actor_kind="admin", actor_id=admin["id"], actor_name=_name(admin),
        details=f"{action.key}: {label}",
    )

    return web.json_response({"ok": True})


async def api_action_hide_image(request):
    from actions import custom as ac
    from database.repository import add_action_custom, unhide_action_image

    body = await request.json()
    admin, chat_id = await _content_perm(request, body)
    action = _action_or_404(body.get("key"))

    image_id = int(body.get("image_id"))
    hidden = bool(body.get("hidden"))

    await unhide_action_image(chat_id, action.key, image_id)

    if hidden:
        await add_action_custom(chat_id, action.key, "hide_image", str(image_id), admin["id"])

    await ac.reload(chat_id)

    audit.log(
        "actions", "hide_image" if hidden else "show_image", chat_id=chat_id,
        actor_kind="admin", actor_id=admin["id"], actor_name=_name(admin),
        details=f"{action.key}: #{image_id}",
    )

    return web.json_response({"ok": True})


async def api_action_hide_builtin(request):
    """Скрыть встроенное слово-триггер или фразу в своей группе."""
    from actions import custom as ac
    from actions.phrases import templates_for
    from database.repository import add_action_custom, list_action_custom

    body = await request.json()
    admin, chat_id = await _content_perm(request, body)
    action = _action_or_404(body.get("key"))

    kind = body.get("kind")
    value = body.get("value") or ""
    hidden = bool(body.get("hidden"))

    if kind == "alias":
        if value not in action.aliases:
            raise web.HTTPBadRequest(text="not a built-in alias")

        # Хотя бы одно слово должно остаться — иначе действие не вызвать
        rows = await list_action_custom(chat_id, action.key)
        already = {r.value for r in rows if r.kind == "hide_alias"}

        if hidden and len(set(action.aliases) - already - {value}) == 0:
            return web.json_response({"ok": False, "error": "Нужно оставить хотя бы одно слово — иначе действие нельзя вызвать"}, status=400)

        stored_kind = "hide_alias"
    elif kind == "phrase":
        if value not in templates_for(action):
            raise web.HTTPBadRequest(text="not a built-in phrase")
        stored_kind = "hide_phrase"
    else:
        raise web.HTTPBadRequest(text="bad kind")

    from database.repository import clear_builtin_hide

    # Сначала убираем старую отметку, потом ставим, если нужно
    await clear_builtin_hide(chat_id, action.key, stored_kind, value)

    if hidden:
        await add_action_custom(chat_id, action.key, stored_kind, value, admin["id"])

    await ac.reload(chat_id)

    audit.log(
        "actions", ("hide_" if hidden else "show_") + kind, chat_id=chat_id,
        actor_kind="admin", actor_id=admin["id"], actor_name=_name(admin),
        details=f"{action.key}: {value.lstrip('=')[:80]}",
    )

    return web.json_response({"ok": True})


async def api_action_replace_image(request):
    """Заменить свою картинку группы новой — ссылкой или загрузкой."""
    from actions import custom as ac
    from database.repository import replace_action_custom_image

    body = await request.json()
    admin, chat_id = await _content_perm(request, body)

    value = str(body.get("value") or "").strip()

    if value.startswith("data:image/"):
        try:
            raw = base64.b64decode(value.split(",", 1)[1])
        except Exception:
            raw = b""

        if not raw or len(raw) > ac.MAX_UPLOAD:
            return web.json_response({"ok": False, "error": "Картинка не читается или больше 2 МБ"}, status=400)
    elif value.startswith("https://"):
        problem = await _check_image_url(value)

        if problem:
            return web.json_response({"ok": False, "error": problem}, status=400)
    else:
        return web.json_response({"ok": False, "error": "Нужна ссылка https://… или файл"}, status=400)

    if not await replace_action_custom_image(chat_id, int(body.get("id")), value):
        raise web.HTTPNotFound(text="not found")

    from webapp.admin import _avatar_cache

    _avatar_cache.pop(f"custom:{int(body.get('id'))}", None)

    await ac.reload(chat_id)

    audit.log(
        "actions", "replace_image", chat_id=chat_id,
        actor_kind="admin", actor_id=admin["id"], actor_name=_name(admin),
        details=f"картинка #{body.get('id')}",
    )

    return web.json_response({"ok": True})


async def api_action_delete_image_global(request):
    """Удалить картинку из общей коллекции для всех групп — только владелец."""
    from database.repository import drop_action_image

    admin, _chats = await _admin(request)

    if not is_owner(admin["id"]):
        raise web.HTTPForbidden(text="owner only")

    body = await request.json()
    await drop_action_image(int(body.get("image_id")))

    audit.log(
        "actions", "delete_image", actor_kind="admin",
        actor_id=admin["id"], actor_name=_name(admin),
        details=f"#{body.get('image_id')} удалена из общей коллекции",
    )

    return web.json_response({"ok": True})


async def api_action_preview(request):
    """«Протестировать»: фраза с подстановками, как её увидит чат."""
    import random as _random

    from actions import custom as ac

    admin, chats = await _admin(request)
    chat_id = _chat_param(request, chats)
    action = _action_or_404(request.query.get("key"))

    customs = ac.get(chat_id).phrases.get(action.key, []) if chat_id else []
    template = _random.choice(customs + _templates_for(action))

    names = {
        "actor": _name(admin),
        "emoji": action.emoji,
        "item": action.item_acc or "",
        "item_instr": action.item_instr or "",
    }

    return web.json_response({
        "male": ac.preview_phrase(template, "male", **names),
        "female": ac.preview_phrase(template, "female", **names),
        "custom": template in customs,
    })


async def _check_image_url(url: str) -> str | None:
    import aiohttp

    try:
        timeout = aiohttp.ClientTimeout(total=10)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers={"User-Agent": "Mozilla/5.0 MaruskaBot"}) as response:
                if response.status != 200:
                    return f"Ссылка не открывается (код {response.status})"

                kind = response.headers.get("Content-Type", "")

                if not kind.startswith("image/"):
                    return "По ссылке не картинка"

                size = int(response.headers.get("Content-Length") or 0)

                if size > 5 * 1024 * 1024:
                    return "Картинка больше 5 МБ — Telegram не примет по ссылке"
    except Exception:
        return "Не удалось открыть ссылку"

    return None


async def api_action_check_image(request):
    await _admin(request)
    body = await request.json()

    problem = await _check_image_url(str(body.get("url") or ""))

    return web.json_response({"ok": problem is None, "error": problem})


async def api_action_custom_image(request):
    """Превью своей картинки группы."""
    from database.repository import get_action_custom

    admin, chats = await _admin(request)
    item = await get_action_custom(int(request.query.get("id", "0") or 0))

    if item is None or item.kind != "image":
        raise web.HTTPNotFound()

    if item.chat_id not in {c["chat_id"] for c in chats} and not is_owner(admin["id"]):
        raise web.HTTPForbidden()

    from webapp.admin import _cached, _download_file

    async def load():
        if item.file_id:
            return await _download_file(request.app["bot"], item.file_id)

        if item.value.startswith("data:"):
            return base64.b64decode(item.value.split(",", 1)[1])

        import aiohttp

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(item.value) as response:
                    if response.status == 200:
                        return await response.read()
        except Exception:
            return None

        return None

    content = await _cached(f"custom:{item.id}", load)

    if not content:
        raise web.HTTPNotFound()

    return web.Response(body=content, content_type="image/jpeg",
                        headers={"Cache-Control": "private, max-age=3600"})


# ---------------------------------------------------------
# Экономика: магазин, массовые изменения, карма, уровни
# ---------------------------------------------------------

async def api_shop_item(request):
    from economy import shop_rules
    from economy.shop import ITEM_BY_KEY
    from database.repository import set_shop_override

    body = await request.json()

    try:
        chat_id = int(body.get("chat_id"))
    except (TypeError, ValueError):
        raise web.HTTPBadRequest(text="chat_id required")

    admin, _chats, _role = await require_perm(request, chat_id, "economy")

    item = ITEM_BY_KEY.get(body.get("key") or "")

    if item is None:
        raise web.HTTPNotFound(text="unknown item")

    def optional_int(name, low, high):
        raw = body.get(name)
        if raw in (None, ""):
            return None
        try:
            return max(low, min(int(raw), high))
        except (TypeError, ValueError):
            raise web.HTTPBadRequest(text=f"bad {name}")

    price = optional_int("price", 1, shop_rules.MAX_PRICE)
    stock = optional_int("stock", 0, 100_000)
    enabled = bool(body.get("enabled", True))

    if price == item.price:
        price = None

    await set_shop_override(chat_id, item.key, price, enabled, stock)
    await shop_rules.reload(chat_id)

    parts = [f"цена {price if price is not None else item.price} 💎"]
    parts.append("в продаже" if enabled else "снят с продажи")
    parts.append(f"склад {stock}" if stock is not None else "без ограничений")

    audit.log(
        "economy", "shop", chat_id=chat_id,
        actor_kind="admin", actor_id=admin["id"], actor_name=_name(admin),
        details=f"{item.emoji} {item.title}: " + ", ".join(parts),
    )

    return web.json_response({"ok": True})


MASS_LIMITS = {"coins": 100_000, "xp": 100_000, "karma": 1_000}


async def api_economy_mass(request):
    """Массовая корректировка алмазов, опыта или кармы по аудитории."""
    from database.repository import add_karma, audience_ids

    body = await request.json()

    try:
        chat_id = int(body.get("chat_id"))
        amount = int(body.get("amount"))
    except (TypeError, ValueError):
        raise web.HTTPBadRequest(text="bad request")

    admin, _chats, _role = await require_perm(request, chat_id, "economy")

    kind = body.get("kind")

    if kind not in MASS_LIMITS:
        raise web.HTTPBadRequest(text="bad kind")

    if not amount or abs(amount) > MASS_LIMITS[kind]:
        return web.json_response(
            {"ok": False, "error": f"Сумма от 1 до {MASS_LIMITS[kind]:,} по модулю".replace(",", " ")},
            status=400,
        )

    audience = body.get("audience") if body.get("audience") in ("all", "active", "vip", "level") else "all"

    try:
        level_min = max(1, int(body.get("level_min") or 1))
    except (TypeError, ValueError):
        level_min = 1

    note = str(body.get("note") or "Массовое начисление").strip()[:80]
    targets = await audience_ids(chat_id, audience, level_min)

    if body.get("dry_run"):
        return web.json_response({"ok": True, "count": len(targets)})

    done = skipped = 0

    for uid in targets:
        try:
            if kind == "coins":
                ok, _balance = await change_balance(
                    telegram_id=uid, amount=amount, reason="admin",
                    note=note, chat_id=chat_id, allow_negative=False,
                )
                if not ok:
                    skipped += 1
                    continue
            elif kind == "xp":
                await award_xp(telegram_id=uid, amount=amount)
            else:
                await add_karma(uid, amount)
            done += 1
        except Exception as error:
            skipped += 1
            logger.warning("MASS %s %s: %s", kind, uid, error)

    labels = {"coins": "💎", "xp": "xp", "karma": "❤️"}
    who = {"all": "всем", "active": "активным", "vip": "VIP", "level": f"с уровня {level_min}"}[audience]

    audit.log(
        "economy", "mass", chat_id=chat_id,
        actor_kind="admin", actor_id=admin["id"], actor_name=_name(admin),
        details=f"{amount:+d} {labels[kind]} {who}: {done} чел." + (f", пропущено {skipped}" if skipped else "") + f" · {note}",
    )

    return web.json_response({"ok": True, "done": done, "skipped": skipped})


async def api_karma(request):
    from database.repository import recent_votes, top_by

    admin, chats = await _admin(request)
    chat_id = _chat_param(request, chats)
    ids = [chat_id] if chat_id else [c["chat_id"] for c in chats]

    return web.json_response({
        "top": await top_by("karma", chat_id),
        "votes": await recent_votes(ids),
    })


async def api_levels(request):
    from database.repository import top_by
    from progress.xp import LEVEL_TITLES, level_title, xp_for_level

    admin, chats = await _admin(request)
    chat_id = _chat_param(request, chats)

    levels = [
        {"level": n, "xp": xp_for_level(n), "title": level_title(n)}
        for n in range(1, 31)
    ]

    return web.json_response({
        "levels": levels,
        "top": await top_by("xp", chat_id),
    })


# ---------------------------------------------------------
# Игры
# ---------------------------------------------------------

MINIGAMES = (
    ("dice", "🎲", "Кубики", "/dice 2d6"),
    ("coin", "🪙", "Монетка", "/coin"),
    ("random", "🎯", "Выбор", "/random пицца суши"),
    ("8ball", "🔮", "Шар судьбы", "/8ball"),
)


async def api_games(request):
    from database.repository import game_stats
    from games.crocodile import game_rules

    admin, chats = await _admin(request)
    chat_id = _chat_param(request, chats)

    week = await action_usage_stats(chat_id, days=7)
    month = await action_usage_stats(chat_id, days=30)

    rules = game_rules(chat_id) if chat_id else None

    return web.json_response({
        "crocodile": {
            "stats": await game_stats(chat_id, 30),
            "rules": rules,
        },
        "minigames": [
            {"key": key, "emoji": emoji, "title": title, "example": example,
             "week": week.get(f"game:{key}", 0), "month": month.get(f"game:{key}", 0)}
            for key, emoji, title, example in MINIGAMES
        ],
    })


# ---------------------------------------------------------
# Память Мары
# ---------------------------------------------------------

async def api_memory(request):
    from database.repository import memory_stats

    admin, chats = await _admin(request)
    chat_id = _chat_param(request, chats, required=True)

    return web.json_response(await memory_stats(chat_id))


async def api_memory_clear(request):
    import context_cache
    from database.repository import clear_memory

    body = await request.json()
    admin, chat_id = await _content_perm(request, body)

    removed = await clear_memory(chat_id)
    context_cache.forget(chat_id)

    audit.log(
        "settings", "memory_clear", chat_id=chat_id,
        actor_kind="admin", actor_id=admin["id"], actor_name=_name(admin),
        details=f"удалено сообщений: {removed}",
    )

    return web.json_response({"ok": True, "removed": removed})


# ---------------------------------------------------------
# Автоответы
# ---------------------------------------------------------

async def api_autoreplies(request):
    from features import autoreplies as ar
    from database.repository import list_autoreplies, save_autoreply

    if request.method == "GET":
        admin, chats = await _admin(request)
        chat_id = _chat_param(request, chats, required=True)

        return web.json_response({
            "rules": [
                {"id": r.id, "trigger": r.trigger, "response": r.response, "match": r.match,
                 "probability": r.probability, "cooldown": r.cooldown, "enabled": r.enabled, "hits": r.hits}
                for r in await list_autoreplies(chat_id)
            ]
        })

    body = await request.json()
    admin, chat_id = await _content_perm(request, body)

    trigger = str(body.get("trigger") or "").strip()
    response = str(body.get("response") or "").strip()
    match = body.get("match") or "contains"
    probability = body.get("probability", 100)
    cooldown = body.get("cooldown", 30)

    error = ar.validate(trigger, response, match, probability, cooldown)

    if error:
        return web.json_response({"ok": False, "error": error}, status=400)

    reply_id = await save_autoreply(chat_id, {
        "trigger": trigger, "response": response, "match": match,
        "probability": int(probability), "cooldown": int(cooldown),
        "enabled": bool(body.get("enabled", True)),
    }, reply_id=int(body["id"]) if body.get("id") else None)

    if not reply_id:
        raise web.HTTPNotFound(text="not found")

    await ar.reload(chat_id)

    audit.log(
        "settings", "autoreply", chat_id=chat_id,
        actor_kind="admin", actor_id=admin["id"], actor_name=_name(admin),
        details=f"«{trigger}» → {response[:60]}",
    )

    return web.json_response({"ok": True, "id": reply_id})


async def api_autoreply_delete(request):
    from features import autoreplies as ar
    from database.repository import delete_autoreply

    body = await request.json()
    admin, chat_id = await _content_perm(request, body)

    if not await delete_autoreply(chat_id, int(body.get("id"))):
        raise web.HTTPNotFound(text="not found")

    await ar.reload(chat_id)

    audit.log(
        "settings", "autoreply_delete", chat_id=chat_id,
        actor_kind="admin", actor_id=admin["id"], actor_name=_name(admin),
    )

    return web.json_response({"ok": True})


# ---------------------------------------------------------
# Источники картинок, категории действий
# ---------------------------------------------------------


async def api_pixabay_search(request):
    """Предпросмотр Pixabay для владельца: только фото, без автопубликации."""
    admin, _chats = await _admin(request)
    if not is_owner(admin["id"]):
        raise web.HTTPForbidden(text="owner only")
    from actions.providers import search_pixabay
    from actions.catalog import ACTION_BY_KEY
    from actions.service import pixabay_profile
    action_key = (request.query.get("action") or "").strip()
    action = ACTION_BY_KEY.get(action_key)
    if action is None:
        raise web.HTTPBadRequest(text="action required")
    try:
        page = max(1, int(request.query.get("page", "1")))
    except ValueError:
        page = 1
    query, required, excluded, filters = pixabay_profile(action, "neutral")
    try:
        photos = await search_pixabay(query, page, required, excluded, filters)
    except Exception as error:
        logger.exception("PIXABAY PREVIEW ERROR")
        raise web.HTTPBadGateway(text=f"Pixabay: {type(error).__name__}: {error}")
    return web.json_response({"action": action.key, "query": query, "page": page, "photos": [{"id": p.photo_id, "url": p.image_url, "fallback_url": p.fallback_url, "tags": p.tags, "provider": p.provider} for p in photos]})


async def api_pixabay_import(request):
    """Импорт выбранных Pixabay-фото в личную библиотеку Telegram."""
    admin, _chats = await _admin(request)
    if not is_owner(admin["id"]):
        raise web.HTTPForbidden(text="owner only")
    body = await request.json(); tag = str(body.get("tag") or "").strip(); photos = body.get("photos") or []
    if not tag: raise web.HTTPBadRequest(text="tag required")
    if not isinstance(photos, list) or not photos: raise web.HTTPBadRequest(text="photos required")
    if len(photos) > 50: raise web.HTTPBadRequest(text="max 50 photos per import")
    import library_core
    from actions.catalog import ACTION_BY_KEY
    from database.repository import add_library_images, ensure_library_collection, set_library_link
    from actions.providers import download_photo

    # Тот же формат, что у загрузки через личку: иначе «мои котики» и
    # «мои_котики» стали бы разными коллекциями, а длинный тег не влез бы
    # в колонку базы (40 символов)
    tag = library_core.normalize_tag(tag)
    if not tag:
        raise web.HTTPBadRequest(text="bad tag")

    # Фото искались под конкретное действие — к нему и привязываем,
    # иначе коллекция нигде не показывалась бы
    action = ACTION_BY_KEY.get(str(body.get("action") or ""))
    await ensure_library_collection(tag, as_action=action is None)
    if action is not None:
        await set_library_link(tag, action.key, True)
    bot = request.app["bot"]; prepared=[]; failed=0
    for item in photos:
        url=str(item.get("url") or "").strip() if isinstance(item,dict) else ""; fallback=str(item.get("fallback_url") or "").strip() if isinstance(item,dict) else ""
        if not url: failed+=1; continue
        content=await download_photo(url,fallback or None)
        if not content: failed+=1; continue
        try:
            from aiogram.types import BufferedInputFile
            msg=await bot.send_photo(chat_id=admin["id"],photo=BufferedInputFile(content,filename=f"pixabay_{item.get('id','image')}.jpg")); photo=msg.photo[-1]; prepared.append((photo.file_id,photo.file_unique_id))
            try: await bot.delete_message(admin["id"],msg.message_id)
            except Exception: pass
        except Exception:
            failed+=1; logger.exception("PIXABAY IMPORT TELEGRAM ERROR")
    imported=duplicates=0
    if prepared: imported,duplicates=await add_library_images(tag,prepared,admin["id"])
    await library_core.reload_links()
    await library_core.reload_collections()
    audit.log("actions","pixabay_import",actor_kind="admin",actor_id=admin["id"],actor_name=_name(admin),details=f"#{tag}: +{imported}, duplicates={duplicates}, failed={failed}")
    return web.json_response({"ok":True,"tag":tag,"imported":imported,"duplicates":duplicates,"failed":failed})

async def api_images(request):
    from actions.providers import KNOWN_PROVIDERS, available_providers, provider_order

    admin, chats = await _admin(request)

    ready = available_providers()
    totals = {}

    for row in await media_stats(limit=1000):
        provider = row["collection"].split("/", 1)[0]
        item = totals.setdefault(provider, {"total": 0, "cached": 0, "used": 0})
        item["total"] += row["total"]
        item["cached"] += row["cached"]
        item["used"] += row["used"]

    order = provider_order()
    listed = order + [name for name in KNOWN_PROVIDERS if name not in order]

    from database.repository import library_summary
    library_total = sum(int(row.get("count") or 0) for row in await library_summary())

    providers = [{
        "name": "library", "label": "Личная библиотека", "builtin": True,
        "ready": True, "active": True, "order": 0,
        "total": library_total, "cached": library_total, "used": 0,
    }]
    providers.extend([
        {"name": name, "label": name, "builtin": False, "ready": name in ready,
         "active": name in order,
         "order": (order.index(name) + 1) if name in order else None,
         **totals.get(name, {"total": 0, "cached": 0, "used": 0})}
        for name in listed
    ])

    return web.json_response({"providers": providers, "owner": is_owner(admin["id"])})


async def api_images_order(request):
    """Порядок источников — настройка всего бота, только владелец."""
    from actions.providers import KNOWN_PROVIDERS, set_provider_order
    from database.repository import set_group_setting

    admin, _chats = await _admin(request)

    if not is_owner(admin["id"]):
        raise web.HTTPForbidden(text="owner only")

    body = await request.json()
    order = [name for name in (body.get("order") or []) if name in KNOWN_PROVIDERS]

    # Личная библиотека встроена в runtime и не входит в список внешних
    # провайдеров. Поэтому отсутствие Pixabay/Unsplash допустимо: бот
    # продолжает работать на уже сохранённых Telegram file_id.

    # Настройки всего бота хранятся в строке с chat_id = 0
    await set_group_setting(chat_id=0, key="provider_order", value=order)
    set_provider_order(order)

    audit.log(
        "settings", "providers", actor_kind="admin",
        actor_id=admin["id"], actor_name=_name(admin), details=" → ".join(order),
    )

    return web.json_response({"ok": True, "order": order})


async def api_actions_category(request):
    body = await request.json()

    try:
        chat_id = int(body.get("chat_id"))
    except (TypeError, ValueError):
        raise web.HTTPBadRequest(text="chat_id required")

    admin, _chats, _role = await require_perm(request, chat_id, "content")

    category = body.get("category")
    enabled = bool(body.get("enabled"))
    keys = [a.key for a in ACTIONS if a.category == category]

    if not keys:
        raise web.HTTPBadRequest(text="unknown category")

    for key in keys:
        await set_action_enabled(chat_id, key, enabled)
        store.set_action_disabled(chat_id, key, not enabled)

    audit.log(
        "actions", "category", chat_id=chat_id,
        actor_kind="admin", actor_id=admin["id"], actor_name=_name(admin),
        details=f"{category}: {'включены' if enabled else 'выключены'} все {len(keys)}",
    )

    return web.json_response({"ok": True, "count": len(keys)})


async def api_analytics(request):
    from database.repository import analytics_summary, game_stats

    admin, chats = await _admin(request)
    chat_id = _chat_param(request, chats)
    ids = [chat_id] if chat_id else [c["chat_id"] for c in chats]

    days = request.query.get("days", "7")
    days = int(days) if days.isdigit() and 1 <= int(days) <= 90 else 7

    offset, tz = _tz_info(chat_id)

    summary = await analytics_summary(ids, days, offset)
    summary["games"] = await game_stats(chat_id, days)
    summary["days"] = days
    summary["tz"] = tz

    return web.json_response(summary)


async def api_group_title(request):
    """Переименовать группу. Нужны право «settings» и право бота менять информацию."""
    from database.repository import set_group_setting
    from webapp.admin import drop_access_cache

    body = await request.json()

    try:
        chat_id = int(body.get("chat_id"))
    except (TypeError, ValueError):
        raise web.HTTPBadRequest(text="chat_id required")

    admin, _chats, _role = await require_perm(request, chat_id, "settings")

    title = str(body.get("title") or "").strip()

    if not 1 <= len(title) <= 128:
        return web.json_response({"ok": False, "error": "Название — от 1 до 128 символов"}, status=400)

    bot = request.app["bot"]
    rights = await bot_rights(bot, chat_id)

    if not rights.get("change_info"):
        return web.json_response(
            {"ok": False, "error": "У Мары нет права «Изменение профиля группы»"}, status=400,
        )

    try:
        await bot.set_chat_title(chat_id, title)
    except Exception as error:
        logger.warning("SET TITLE %s: %s", chat_id, error)
        return web.json_response({"ok": False, "error": "Telegram не дал переименовать группу"}, status=400)

    # Название в базе — чтобы панель сразу показывала новое
    await set_group_setting(chat_id=chat_id, key="_title", value=title, title=title)
    drop_access_cache(admin["id"])

    audit.log(
        "settings", "title", chat_id=chat_id,
        actor_kind="admin", actor_id=admin["id"], actor_name=_name(admin), details=title,
    )

    return web.json_response({"ok": True})


async def api_punish_rules(request):
    """Свои правила наказаний группы: список и сохранение."""
    from features import automod
    from database.repository import MAX_RULES, list_punish_rules, save_punish_rule

    def as_dict(r):
        rule = {"violation": r.violation, "count": r.count, "window": r.window_minutes,
                "action": r.action, "duration": r.duration_minutes}
        return {"id": r.id, "enabled": r.enabled, "text": automod.describe_rule(rule), **rule}

    if request.method == "GET":
        admin, chats = await _admin(request)
        chat_id = _chat_param(request, chats, required=True)

        return web.json_response({
            "rules": [as_dict(r) for r in await list_punish_rules(chat_id)],
            "violations": [{"key": "any", "title": "любое нарушение"}]
                          + [{"key": k, "title": automod.REASONS[k]} for k in automod.VIOLATIONS],
            "max": MAX_RULES,
        })

    body = await request.json()

    try:
        chat_id = int(body.get("chat_id"))
        count = int(body.get("count"))
        window = int(body.get("window"))
        duration = int(body.get("duration") or 60)
    except (TypeError, ValueError):
        raise web.HTTPBadRequest(text="bad numbers")

    admin, _chats, _role = await require_perm(request, chat_id, "moderation")

    violation = body.get("violation")
    action = body.get("action")

    error = None

    if violation not in ("any",) + automod.VIOLATIONS:
        error = "Неизвестное нарушение"
    elif action not in automod.RULE_ACTIONS:
        error = "Неизвестное действие"
    elif not 1 <= count <= 50:
        error = "Сколько раз — от 1 до 50"
    elif not 1 <= window <= 10080:
        error = "Окно — от 1 минуты до недели"
    elif action in ("mute", "tempban") and not 1 <= duration <= 43200:
        error = "Срок — от 1 минуты до 30 дней"
    elif action in ("ban", "tempban") and count == 1 and not body.get("confirm_strict"):
        # Бан за первое же нарушение — только осознанно
        return web.json_response({"ok": False, "needs_confirm": True,
                                  "error": "Бан за первое же нарушение — подтверди, что это намеренно"}, status=400)

    if error:
        return web.json_response({"ok": False, "error": error}, status=400)

    data = {"violation": violation, "count": count, "window_minutes": window,
            "action": action, "duration_minutes": duration, "enabled": bool(body.get("enabled", True))}

    rule_id = await save_punish_rule(chat_id, data, int(body["id"]) if body.get("id") else None)

    if rule_id == -1:
        return web.json_response({"ok": False, "error": f"Не больше {MAX_RULES} правил"}, status=400)

    if not rule_id:
        raise web.HTTPNotFound(text="not found")

    await automod.reload_rules(chat_id)

    text = automod.describe_rule({"violation": violation, "count": count, "window": window,
                                  "action": action, "duration": duration})

    audit.log("moderation", "rule", chat_id=chat_id, actor_kind="admin",
              actor_id=admin["id"], actor_name=_name(admin), details=text)

    return web.json_response({"ok": True, "id": rule_id, "text": text})


async def api_punish_rule_delete(request):
    from features import automod
    from database.repository import delete_punish_rule

    body = await request.json()
    chat_id = int(body.get("chat_id"))
    admin, _chats, _role = await require_perm(request, chat_id, "moderation")

    if not await delete_punish_rule(chat_id, int(body.get("id"))):
        raise web.HTTPNotFound(text="not found")

    await automod.reload_rules(chat_id)
    audit.log("moderation", "rule_delete", chat_id=chat_id, actor_kind="admin",
              actor_id=admin["id"], actor_name=_name(admin))

    return web.json_response({"ok": True})


async def api_punish_rule_move(request):
    from features import automod
    from database.repository import move_punish_rule

    body = await request.json()
    chat_id = int(body.get("chat_id"))
    await require_perm(request, chat_id, "moderation")

    await move_punish_rule(chat_id, int(body.get("id")), -1 if body.get("direction") == "up" else 1)
    await automod.reload_rules(chat_id)

    return web.json_response({"ok": True})


# ---------------------------------------------------------
# Своя коллекция картинок (владелец)
# ---------------------------------------------------------

async def _owner(request):
    admin, chats = await _admin(request)

    if not is_owner(admin["id"]):
        raise web.HTTPForbidden(text="owner only")

    return admin, chats


def _targets() -> list[dict]:
    import images_library

    return [{"key": images_library.CATS, "title": "🐱 Котики (мяу, покажи меня)"}] + [
        {"key": a.key, "title": f"{a.emoji} {(a.item_acc or a.key).capitalize()}"}
        for a in sorted(ACTIONS, key=lambda a: (a.item_acc or a.key))
    ]


async def api_library(request):
    import images_library
    from database.repository import library_summary

    admin, chats = await _owner(request)

    from database.repository import list_library_collections

    collections = await library_summary()
    metas = {m.tag: m for m in await list_library_collections()}
    seen = {c["tag"] for c in collections}

    # Категории, созданные в панели, но ещё без фото
    for tag in metas:
        if tag not in seen:
            collections.append({"tag": tag, "count": 0, "shows": 0, "updated": None, "targets": []})

    for c in collections:
        m = metas.get(c["tag"])
        c.update({
            "emoji": m.emoji if m else "🖼",
            "as_action": bool(m.as_action) if m else False,
            "triggers": list(m.triggers or []) if m else [],
            "phrase": m.phrase if m else None,
        })

    collections.sort(key=lambda c: c["tag"])
    covered = {t for c in collections for t in c["targets"]}
    usage = await action_usage_stats(None, days=30)

    # Какие действия чаще всего зовут, а своих картинок у них нет
    missing = sorted(
        ({"key": a.key, "emoji": a.emoji, "title": (a.item_acc or a.key).capitalize(), "usage": usage.get(a.key, 0)}
         for a in ACTIONS if a.key not in covered),
        key=lambda x: -x["usage"],
    )[:30]

    return web.json_response({
        "collections": collections,
        "missing": missing,
        "cats_covered": images_library.CATS in covered,
        "targets": _targets(),
    })


async def api_library_images(request):
    from database.repository import library_images

    await _owner(request)
    tag = (request.query.get("tag") or "")[:40]
    limit = min(max(int(request.query.get("limit", "60") or 60), 1), 600)

    return web.json_response({"tag": tag, "images": await library_images(tag, limit=limit)})


async def api_library_image(request):
    from database.repository import library_image
    from webapp.admin import _cached, _download_file

    await _owner(request)
    row = await library_image(int(request.query.get("id", "0") or 0))

    if row is None:
        raise web.HTTPNotFound()

    content = await _cached(f"library:{row.id}", lambda: _download_file(request.app["bot"], row.file_id))

    if not content:
        raise web.HTTPNotFound()

    return web.Response(body=content, content_type="image/jpeg",
                        headers={"Cache-Control": "private, max-age=3600"})


async def api_library_link(request):
    import images_library
    from database.repository import set_library_link

    admin, _chats = await _owner(request)
    body = await request.json()

    tag = images_library.normalize_tag(body.get("tag"))
    target = body.get("target")

    if not tag or target not in {t["key"] for t in _targets()}:
        raise web.HTTPBadRequest(text="bad tag or target")

    await set_library_link(tag, target, bool(body.get("linked")))
    await images_library.reload_links()

    audit.log("actions", "library_link", actor_kind="admin", actor_id=admin["id"], actor_name=_name(admin),
              details=f"#{tag} {'→' if body.get('linked') else '✕'} {target}")

    return web.json_response({"ok": True})


async def api_library_collection(request):
    """Создать категорию заранее или настроить её как действие."""
    import images_library
    from actions import custom as ac
    from actions.catalog import find_action
    from database.repository import ensure_library_collection, update_library_collection

    admin, _chats = await _owner(request)
    body = await request.json()

    tag = images_library.normalize_tag(body.get("tag"))

    if not tag or len(tag) < 2:
        return web.json_response({"ok": False, "error": "Название — хотя бы 2 буквы"}, status=400)

    if body.get("create"):
        clash = find_action(tag)
        created = await ensure_library_collection(tag, as_action=clash is None)

        if not created:
            return web.json_response({"ok": False, "error": "Такая коллекция уже есть"}, status=400)

        if clash is not None:
            from database.repository import set_library_link
            await set_library_link(tag, clash.key, True)
    else:
        await ensure_library_collection(tag, as_action=True)

    data = {}

    if "emoji" in body:
        data["emoji"] = (str(body.get("emoji") or "").strip() or "✨")[:8]

    if "as_action" in body:
        data["as_action"] = bool(body.get("as_action"))

    if "triggers" in body:
        triggers = []

        for raw in (body.get("triggers") or [])[:10]:
            word = ac.normalize_alias(str(raw))
            problem = ac.validate_alias(word)

            if problem:
                return web.json_response({"ok": False, "error": f"«{raw}»: {problem}"}, status=400)

            clash = find_action(word)

            if clash is not None:
                return web.json_response(
                    {"ok": False, "error": f"«{word}» уже запускает встроенное действие «{clash.item_acc or clash.key}»"},
                    status=400,
                )

            if word != tag and word not in triggers:
                triggers.append(word)

        data["triggers"] = triggers

    if "phrase" in body:
        phrase = str(body.get("phrase") or "").strip()

        if phrase:
            problem = ac.validate_phrase(phrase)

            if problem:
                return web.json_response({"ok": False, "error": problem}, status=400)

        data["phrase"] = phrase or None

    if data:
        await update_library_collection(tag, data)

    await images_library.reload_links()
    await images_library.reload_collections()

    audit.log("actions", "library_collection", actor_kind="admin", actor_id=admin["id"],
              actor_name=_name(admin), details=f"#{tag}: " + ", ".join(sorted(data)) if data else f"#{tag}: создана")

    return web.json_response({"ok": True, "tag": tag})


async def api_library_delete(request):
    import images_library
    from database.repository import delete_library_collection, delete_library_image

    admin, _chats = await _owner(request)
    body = await request.json()

    if body.get("id"):
        ok = await delete_library_image(int(body["id"]))
        details = f"картинка #{body['id']}"
    else:
        tag = images_library.normalize_tag(body.get("tag"))
        if not tag:
            raise web.HTTPBadRequest(text="bad tag")
        ok = await delete_library_collection(tag) >= 0
        await images_library.reload_links()
        await images_library.reload_collections()
        details = f"коллекция #{tag}"

    audit.log("actions", "library_delete", actor_kind="admin", actor_id=admin["id"], actor_name=_name(admin),
              details=details)

    return web.json_response({"ok": ok})


async def api_groups(request):
    """Группы, которыми управляет админ (синоним данных из /session)."""
    _admin_user, chats = await _admin(request)
    return web.json_response({"groups": chats})


async def api_moderation(request):
    """Сводка модерации: нарушители и последние действия."""
    admin, chats = await _admin(request)
    chat_id = _chat_param(request, chats)
    ids = [chat_id] if chat_id else [c["chat_id"] for c in chats]

    return web.json_response({
        "violators": await recent_violators(chat_id, ids, limit=20),
        "events": await list_audit(ids, category="moderation", limit=30),
    })


def setup_v2_routes(app: web.Application) -> None:
    app.router.add_get("/api/admin/me", api_me)
    app.router.add_get("/api/admin/dashboard", api_dashboard)
    app.router.add_get("/api/admin/journal", api_journal)
    app.router.add_get("/api/admin/violators", api_violators)
    app.router.add_post("/api/admin/warnings/clear", api_clear_warnings)
    app.router.add_get("/api/admin/roles", api_roles)
    app.router.add_post("/api/admin/roles", api_roles)
    app.router.add_get("/api/admin/actions", api_actions)
    app.router.add_post("/api/admin/actions/toggle", api_action_toggle)
    app.router.add_get("/api/admin/action_image", api_action_image)
    app.router.add_get("/api/admin/broadcasts", api_broadcasts)
    app.router.add_post("/api/admin/broadcasts", api_broadcasts)
    app.router.add_post("/api/admin/broadcasts/cancel", api_broadcast_cancel)
    app.router.add_post("/api/admin/broadcasts/test", api_broadcast_test)
    app.router.add_post("/api/admin/broadcasts/audience", api_broadcast_audience)
    app.router.add_get("/api/admin/punish_rules", api_punish_rules)
    app.router.add_post("/api/admin/punish_rules", api_punish_rules)
    app.router.add_post("/api/admin/punish_rules/delete", api_punish_rule_delete)
    app.router.add_post("/api/admin/punish_rules/move", api_punish_rule_move)
    app.router.add_get("/api/admin/analytics", api_analytics)
    app.router.add_get("/api/admin/heatmap", api_heatmap)
    app.router.add_get("/api/admin/notifications", api_notifications)
    app.router.add_get("/api/admin/search", api_search)
    app.router.add_post("/api/admin/undo", api_undo)
    app.router.add_get("/api/admin/action", api_action_detail)
    app.router.add_get("/api/admin/action/preview", api_action_preview)
    app.router.add_get("/api/admin/action/custom_image", api_action_custom_image)
    app.router.add_post("/api/admin/action/custom", api_action_custom)
    app.router.add_post("/api/admin/action/custom/delete", api_action_custom_delete)
    app.router.add_post("/api/admin/action/option", api_action_option)
    app.router.add_post("/api/admin/action/hide_image", api_action_hide_image)
    app.router.add_post("/api/admin/action/delete_image", api_action_delete_image_global)
    app.router.add_post("/api/admin/action/check_image", api_action_check_image)
    app.router.add_post("/api/admin/action/hide_builtin", api_action_hide_builtin)
    app.router.add_post("/api/admin/action/replace_image", api_action_replace_image)
    app.router.add_post("/api/admin/shop/item", api_shop_item)
    app.router.add_post("/api/admin/economy/mass", api_economy_mass)
    app.router.add_get("/api/admin/karma", api_karma)
    app.router.add_get("/api/admin/levels", api_levels)
    app.router.add_get("/api/admin/games", api_games)
    app.router.add_get("/api/admin/memory", api_memory)
    app.router.add_post("/api/admin/memory/clear", api_memory_clear)
    app.router.add_get("/api/admin/autoreplies", api_autoreplies)
    app.router.add_post("/api/admin/autoreplies", api_autoreplies)
    app.router.add_post("/api/admin/autoreplies/delete", api_autoreply_delete)
    app.router.add_get("/api/admin/pixabay/search", api_pixabay_search)
    app.router.add_post("/api/admin/pixabay/import", api_pixabay_import)
    app.router.add_get("/api/admin/images", api_images)
    app.router.add_post("/api/admin/images/order", api_images_order)
    app.router.add_post("/api/admin/group/title", api_group_title)

    app.router.add_get("/api/admin/library", api_library)
    app.router.add_get("/api/admin/library/images", api_library_images)
    app.router.add_get("/api/admin/library/image", api_library_image)
    app.router.add_post("/api/admin/library/link", api_library_link)
    app.router.add_post("/api/admin/library/delete", api_library_delete)
    app.router.add_post("/api/admin/library/collection", api_library_collection)

    # Синонимы по схеме концепции
    app.router.add_get("/api/admin/groups", api_groups)
    app.router.add_get("/api/admin/moderation", api_moderation)
    app.router.add_get("/api/admin/admins", api_roles)
    app.router.add_post("/api/admin/admins", api_roles)
    app.router.add_post("/api/admin/actions/category", api_actions_category)
