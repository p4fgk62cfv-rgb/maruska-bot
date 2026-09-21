"""
Настройки группы в памяти.

Фильтры сообщений синхронные и вызываются на каждое сообщение,
поэтому ходить в базу оттуда нельзя. Значения кэшируются, база
остаётся источником правды.

Кэш прогревается мидлварью до того, как отработают фильтры.
"""

from settings.registry import DEFAULTS


_cache: dict[int, dict[str, bool]] = {}


def is_loaded(chat_id: int) -> bool:
    return chat_id in _cache


def prime(chat_id: int, values: dict | None) -> dict[str, bool]:
    merged = dict(DEFAULTS)

    for key, value in (values or {}).items():
        if key in merged:
            merged[key] = bool(value)

    _cache[chat_id] = merged
    return merged


def values(chat_id: int) -> dict[str, bool]:
    return _cache.get(chat_id) or dict(DEFAULTS)


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


def apply(chat_id: int, key: str, value: bool) -> None:
    current = _cache.setdefault(chat_id, dict(DEFAULTS))
    current[key] = bool(value)


def forget(chat_id: int) -> None:
    _cache.pop(chat_id, None)
