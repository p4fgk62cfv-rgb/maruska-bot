"""
Роли администраторов и их права в веб-панели.

Если роль в группе не назначена явно, она берётся из Telegram:
создатель группы — главный администратор, остальные админы —
модераторы. Владелец бота (OWNER_IDS) может всё везде.

Права панели дополнительно ограничены реальными правами бота:
кнопка бана бессмысленна, если сам бот не умеет банить.
"""

import time

from settings.handler import is_owner


ROLES = {
    "owner": ("👑", "Владелец", "Всё, во всех группах"),
    "super_admin": ("⭐", "Главный админ", "Всё в своей группе"),
    "moderator": ("🛡", "Модератор", "Модерация и журнал"),
    "economy": ("💎", "Экономист", "Алмазы, магазин, достижения"),
    "games": ("🎮", "Игровой админ", "Игры и их настройки"),
    "content": ("⚡", "Контент", "Действия, приветствия, рассылки"),
    "analytics": ("📊", "Аналитик", "Только просмотр статистики"),
}

ASSIGNABLE = ("super_admin", "moderator", "economy", "games", "content", "analytics")


PERMISSIONS = {
    "owner": {"*"},
    "super_admin": {
        "view", "settings", "moderation", "economy", "games",
        "content", "broadcast", "roles", "journal",
    },
    "moderator": {"view", "moderation", "journal"},
    "economy": {"view", "economy", "journal"},
    "games": {"view", "games"},
    "content": {"view", "content", "broadcast"},
    "analytics": {"view"},
}


# Какие настройки к какому праву относятся — по разделу панели
SECTION_PERMISSION = {
    "Общение": "content",
    "Сообщество": "settings",
    "Модерация": "moderation",
    "Развлечения": "games",
}


def can(role: str | None, permission: str) -> bool:
    allowed = PERMISSIONS.get(role or "", set())
    return "*" in allowed or permission in allowed


_role_cache: dict[tuple[int, int], tuple[float, str | None]] = {}

ROLE_TTL = 120


async def resolve_role(bot, chat_id: int, user_id: int) -> str | None:
    """
    Роль человека в группе. None — не админ.
    """
    if is_owner(user_id):
        return "owner"

    key = (chat_id, user_id)
    cached = _role_cache.get(key)

    if cached and time.monotonic() - cached[0] < ROLE_TTL:
        return cached[1]

    from database.repository import get_role

    role = None

    try:
        member = await bot.get_chat_member(chat_id, user_id)
        status = member.status
    except Exception:
        status = None

    if status in ("creator", "administrator"):
        role = await get_role(chat_id, user_id)

        if role not in PERMISSIONS:
            role = "super_admin" if status == "creator" else "moderator"

    _role_cache[key] = (time.monotonic(), role)

    return role


def forget_role(chat_id: int, user_id: int) -> None:
    _role_cache.pop((chat_id, user_id), None)


_rights_cache: dict[int, tuple[float, dict]] = {}


async def bot_rights(bot, chat_id: int) -> dict:
    """
    Что сам бот умеет в группе — чтобы панель не предлагала
    невыполнимое.
    """
    cached = _rights_cache.get(chat_id)

    if cached and time.monotonic() - cached[0] < 300:
        return cached[1]

    # present: Мара вообще состоит в группе (её не удалили, группа существует)
    rights = {"present": False, "admin": False, "restrict": False, "delete": False, "pin": False, "change_info": False}

    try:
        me = await bot.me()
        member = await bot.get_chat_member(chat_id, me.id)

        rights["present"] = member.status not in ("left", "kicked")

        if member.status in ("administrator", "creator"):
            rights = {
                "present": True,
                "admin": True,
                "restrict": bool(getattr(member, "can_restrict_members", False)),
                "delete": bool(getattr(member, "can_delete_messages", False)),
                "pin": bool(getattr(member, "can_pin_messages", False)),
                "change_info": bool(getattr(member, "can_change_info", False)),
            }
    except Exception:
        pass

    _rights_cache[chat_id] = (time.monotonic(), rights)

    return rights
