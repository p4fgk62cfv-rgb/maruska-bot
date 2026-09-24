"""
Контекст разговора в памяти процесса.

Раньше каждый ответ начинался с запроса к Postgres за последними
сообщениями. На удалённой базе это лишние сотни миллисекунд перед
каждой репликой.

Теперь последние сообщения держатся в памяти, а база остаётся
источником правды при перезапуске: кэш для чата подтягивается
из неё один раз, при первом обращении.
"""

from collections import defaultdict, deque

MAX_CACHED = 24

_cache: dict[int, deque[str]] = defaultdict(lambda: deque(maxlen=MAX_CACHED))
_loaded: set[int] = set()


def remember(chat_id: int, username: str | None, text: str) -> None:
    _cache[chat_id].append(f"{username or 'Пользователь'}: {text}")


def is_loaded(chat_id: int) -> bool:
    return chat_id in _loaded


def prime(chat_id: int, messages: list[str]) -> None:
    """
    Первичная заливка из базы после перезапуска.
    Уже накопленное в памяти дописывается сверху.
    """
    existing = list(_cache[chat_id])
    combined = messages + [m for m in existing if m not in messages]

    _cache[chat_id] = deque(combined[-MAX_CACHED:], maxlen=MAX_CACHED)
    _loaded.add(chat_id)


def recent(chat_id: int, limit: int) -> list[str]:
    items = list(_cache[chat_id])
    return items[-limit:] if limit > 0 else items


def forget(chat_id: int) -> None:
    """Очистка памяти группы из панели — сбрасываем и кэш."""
    _cache.pop(chat_id, None)
    _loaded.discard(chat_id)
