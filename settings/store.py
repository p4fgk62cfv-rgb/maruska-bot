"""
Настройки группы в памяти.

Фильтры сообщений синхронные и вызываются на каждое сообщение,
поэтому ходить в базу оттуда нельзя. Значения кэшируются, база
остаётся источником правды.

Кэш прогревается мидлварью до того, как отработают фильтры.
"""

from settings.registry import (
    CHOICE_BY_KEY,
    DEFAULTS,
    NUMBER_BY_KEY,
    TEXT_BY_KEY,
)


_cache: dict[int, dict] = {}


def is_loaded(chat_id: int) -> bool:
    return chat_id in _cache


def prime(chat_id: int, values: dict | None) -> dict:
    merged = dict(DEFAULTS)

    for key, value in (values or {}).items():
        if key not in merged:
            continue

        if key in CHOICE_BY_KEY:
            # Значение из списка: принимаем только известные варианты
            allowed = {option[0] for option in CHOICE_BY_KEY[key].options}
            if value in allowed:
                merged[key] = value

        elif key in NUMBER_BY_KEY:
            # Число: приводим к границам, мусор игнорируем
            try:
                merged[key] = NUMBER_BY_KEY[key].clamp(int(value))
            except (TypeError, ValueError):
                pass

        elif key in TEXT_BY_KEY:
            spec = TEXT_BY_KEY[key]

            if isinstance(value, str) and (value.strip() or spec.allow_empty):
                merged[key] = value[: spec.max_length]

        else:
            merged[key] = bool(value)

    _cache[chat_id] = merged
    return merged


def values(chat_id: int) -> dict:
    return _cache.get(chat_id) or dict(DEFAULTS)


def get_value(chat_id: int | None, key: str) -> str:
    """
    Значение настройки-списка (например, характера Мары).
    """
    if chat_id is None or chat_id >= 0:
        return DEFAULTS.get(key, "")

    return values(chat_id).get(key, DEFAULTS.get(key, ""))


def is_enabled(chat_id: int | None, key: str) -> bool:
    """
    Главная проверка. В личке ограничений нет: настройки
    существуют для групп.
    """
    if chat_id is None:
        return DEFAULTS.get(key, True)

    if chat_id >= 0:
        return True

    return values(chat_id).get(key, DEFAULTS.get(key, True))


def apply(chat_id: int, key: str, value) -> None:
    current = _cache.setdefault(chat_id, dict(DEFAULTS))

    if key in CHOICE_BY_KEY:
        current[key] = value
    elif key in NUMBER_BY_KEY:
        current[key] = NUMBER_BY_KEY[key].clamp(int(value))
    elif key in TEXT_BY_KEY:
        current[key] = str(value)[: TEXT_BY_KEY[key].max_length]
    else:
        current[key] = bool(value)


def get_number(chat_id: int | None, key: str) -> int:
    """
    Числовая настройка группы. В личке и при отсутствии записи
    берётся значение по умолчанию.
    """
    number = NUMBER_BY_KEY.get(key)
    fallback = DEFAULTS.get(key, 0)

    if chat_id is None or chat_id >= 0:
        return int(fallback)

    value = values(chat_id).get(key, fallback)

    try:
        value = int(value)
    except (TypeError, ValueError):
        return int(fallback)

    return number.clamp(value) if number else value


def get_text(chat_id: int | None, key: str) -> str:
    """
    Текстовая настройка группы. Пусто или не задано — стандартный текст.
    """
    fallback = DEFAULTS.get(key, "")

    if chat_id is None or chat_id >= 0:
        return str(fallback)

    stored = values(chat_id).get(key)

    # Пустое значение у списка — осознанный выбор, а не «не задано»
    if stored == "" and key in TEXT_BY_KEY and TEXT_BY_KEY[key].allow_empty:
        return ""

    return str(stored or fallback)


# Заблокированные: держим в памяти, чтобы проверка в фильтрах
# не ходила в базу на каждое сообщение.
_blocked: dict[int, set[int]] = {}


def prime_blocked(chat_id: int, ids: set[int]) -> None:
    _blocked[chat_id] = set(ids)


def is_blocked(chat_id: int | None, user_id: int | None) -> bool:
    if chat_id is None or user_id is None or chat_id >= 0:
        return False

    return user_id in _blocked.get(chat_id, ())


def set_blocked(chat_id: int, user_id: int, blocked: bool) -> None:
    ids = _blocked.setdefault(chat_id, set())

    if blocked:
        ids.add(user_id)
    else:
        ids.discard(user_id)


_disabled_actions: dict[int, set[str]] = {}


def prime_actions(chat_id: int, keys: set[str]) -> None:
    _disabled_actions[chat_id] = set(keys)


def is_action_disabled(chat_id: int | None, key: str) -> bool:
    if chat_id is None or chat_id >= 0:
        return False
    return key in _disabled_actions.get(chat_id, ())


def set_action_disabled(chat_id: int, key: str, disabled: bool) -> None:
    keys = _disabled_actions.setdefault(chat_id, set())
    (keys.add if disabled else keys.discard)(key)


def forget(chat_id: int) -> None:
    _cache.pop(chat_id, None)



# ---------------------------------------------------------
# Часовой пояс группы
# ---------------------------------------------------------

def zone(chat_id: int | None):
    """ZoneInfo группы; при любой ошибке — UTC."""
    from datetime import timezone as _tz

    try:
        from zoneinfo import ZoneInfo

        name = get_value(chat_id, "timezone") if chat_id and chat_id < 0 else "UTC"
        return ZoneInfo(name or "UTC")
    except Exception:
        return _tz.utc


def local_now(chat_id: int | None):
    from datetime import datetime as _dt

    return _dt.now(zone(chat_id))


def utc_offset_hours(chat_id: int | None) -> int:
    """Смещение от UTC в целых часах сейчас (для сдвига часовых графиков)."""
    offset = local_now(chat_id).utcoffset()
    return int(offset.total_seconds() // 3600) if offset else 0
