"""
Доступ групп к функциям Мары — решает владелец бота, а не админы группы.

Новая группа, куда добавили Мару, получает только базовое: /help, /settings,
приветствие новичков. Остальное разбито на модули (Арена и турниры, рыбалка,
игры, разговор с Марой…), и каждый модуль владелец включает этой группе сам —
в панели, раздел «Доступ групп». Пока модуль выключен, Мара на его команды не
отвечает (на команду — один раз в 10 минут объясняет, что это включает владелец),
а его фоновые рассылки (реклама Арены, итоги недели, дни рождения) в группу не идут.

Группы, где Мара была до появления этого раздела, получили всё — один раз,
при первом запуске (флаг access_initialized в общих настройках).

Хранится в настройках группы под ключом owner_access: {"all": true} — всё
разрешено, иначе {"modules": [...]}. Проверка синхронная (фильтры роутеров),
поэтому доступ всех групп держится в памяти: грузится при старте, меняется
сразу при каждом переключении в панели.
"""

import logging

logger = logging.getLogger("maruska.access")

KEY = "owner_access"
# Кому писать, чтобы группе открыли функции: Мара отвечает так в закрытой группе
CONTACT = "@uastas"
FLAG = "access_initialized"

# Модуль → (название, что в него входит). Порядок — как в панели.
MODULES: dict[str, tuple[str, str]] = {
    "arena": ("🃏 Арена и турниры", "/game, «/старт турнир», турниры групп, реклама Арены"),
    "fishing": ("🎣 Рыбалка", "/fishing, «Мара, рыбалка», топ рыбаков"),
    "games": ("🎲 Игры", "крокодил, кости, игровой стол"),
    "chat": ("💬 Разговор с Марой", "ответы на «Мара, …», автоответы, реакции на сообщения"),
    "actions": ("🤗 Действия с картинками", "обнять, пиво, баня — 200 действий"),
    "draw": ("🎨 Рисунки", "«Мара, нарисуй …»"),
    "social": ("💞 Пары и праздники", "пара дня, браки, дни рождения, гармония, «кто я», шансы"),
    "economy": ("💎 Алмазы и статистика", "алмазы, магазин, опыт, рейтинг, топы, итоги недели"),
    "moderation": ("🛡 Модерация", "антимат, автомодерация, капча, муты и баны"),
    "media": ("📻 Радио, погода, котики", "радио, погода, котики, гадания"),
}

_cache: dict[int, dict] = {}
_loaded = False


def allowed(chat_id: int | None, module: str) -> bool:
    """Можно ли модуль в этой группе. В личке ограничений нет; до загрузки — всё можно (не запирать всех)."""
    if chat_id is None or chat_id >= 0 or not _loaded:
        return True
    entry = _cache.get(chat_id)
    if not entry:
        return False
    return bool(entry.get("all")) or module in (entry.get("modules") or ())


def entry(chat_id: int) -> dict:
    """Доступ группы для панели: {"all": bool, "modules": [...]}."""
    raw = _cache.get(chat_id) or {}
    return {"all": bool(raw.get("all")), "modules": [m for m in raw.get("modules") or () if m in MODULES]}


def clean(value) -> dict:
    if not isinstance(value, dict):
        return {}
    if value.get("all"):
        return {"all": True}
    return {"modules": [m for m in value.get("modules") or () if m in MODULES]}


async def load() -> int:
    """При старте: доступ всех групп в память; в первый раз — всё уже знакомым группам."""
    global _loaded
    from database.repository import all_group_values, get_group_settings, list_known_chats, set_group_setting

    rows = {chat_id: clean(values.get(KEY)) for chat_id, values in (await all_group_values()).items()}
    if not (await get_group_settings(0)).get(FLAG):
        known = {int(chat["chat_id"]) for chat in await list_known_chats()} | set(rows)
        granted = 0
        for chat_id in known:
            if chat_id < 0 and not rows.get(chat_id):
                await set_group_setting(chat_id, KEY, {"all": True})
                rows[chat_id] = {"all": True}
                granted += 1
        await set_group_setting(0, FLAG, True)
        logger.info("ACCESS: группам, где Мара уже была, открыто всё: %s", granted)
    _cache.clear()
    _cache.update({chat_id: value for chat_id, value in rows.items() if value})
    _loaded = True
    return len(_cache)


async def set_access(chat_id: int, *, everything: bool | None = None, module: str | None = None,
                     on: bool | None = None) -> dict:
    """Панель владельца: всё разом или один модуль. Возвращает новый доступ группы."""
    from database.repository import set_group_setting

    current = entry(chat_id)
    if everything is not None:
        # «Всё» выключили — дальше модули включаются по одному, начиная с ничего
        value = {"all": True} if everything else {"modules": []}
    elif module in MODULES and on is not None:
        modules = list(MODULES) if current["all"] else list(current["modules"])
        if on and module not in modules:
            modules.append(module)
        if not on and module in modules:
            modules.remove(module)
        value = {"all": True} if set(modules) >= set(MODULES) else {"modules": [m for m in MODULES if m in modules]}
    else:
        return current
    await set_group_setting(chat_id, KEY, value)
    _cache[chat_id] = value
    return entry(chat_id)


def move(old_id: int, new_id: int) -> None:
    """Группа стала супергруппой: доступ переезжает на новый ID (в базе его переносит move_chat)."""
    if old_id in _cache:
        _cache[new_id] = _cache.pop(old_id)


def router_filter(module: str):
    """Фильтр роутера: в группе без доступа к модулю его обработчики не срабатывают."""
    def check(event) -> bool:
        message = event if hasattr(event, "chat") else getattr(event, "message", None)
        chat = getattr(message, "chat", None)
        return chat is None or allowed(chat.id, module)

    return check
