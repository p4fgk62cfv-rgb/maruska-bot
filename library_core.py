"""
Своя коллекция картинок — логика без Telegram.

Названия и хэштеги, слова-триггеры, коллекции как действия,
привязки к действиям, выбор картинки. Здесь нет aiogram, поэтому
модуль можно импортировать из поиска действий и проверять тестами.
Загрузка фото через личку — в images_library.py.
"""

import logging
import re

from settings.store import is_enabled


logger = logging.getLogger("maruska.library")


CATS = "cats"
PAIR = "pair_of_day"
PAIR_WORDS = {"пара дня", "парадня", "пара", "пары", "влюбленные", "любовь"}

CAT_WORDS = {"кошки", "кошка", "котики", "котик", "коты", "кот", "котята", "cats", "cat", "мяу"}

ALBUM_WAIT = 2.0        # секунд: Telegram присылает альбом отдельными сообщениями
TAG_MEMORY = 120        # секунд: столько помним последний хэштег для следующих пачек
REPORT_WAIT = 4.0       # секунд тишины — и Мара присылает один общий отчёт
MAX_TAG = 40


# ---------------------------------------------------------
# Чистые функции — покрыты тестами
# ---------------------------------------------------------

def normalize_tag(text: str) -> str | None:
    """«#Пиво» → «пиво», «#мои_котики» → «мои котики». Пусто — None."""
    tag = (text or "").strip().lstrip("#").replace("_", " ").lower().replace("ё", "е")
    tag = " ".join(re.sub(r"[^\w\s-]", " ", tag).split())[:MAX_TAG]
    return tag or None


def tag_from_caption(caption: str | None) -> str | None:
    """Первый хэштег из подписи: «вот #пиво холодное» → «пиво»."""
    match = re.search(r"#([\w-]+)", caption or "")
    return normalize_tag(match.group(1)) if match else None


def resolve_tag(caption_tag: str | None, last: tuple | None, now: float,
                ttl: float = TAG_MEMORY) -> str | None:
    """
    Хэштег для пачки фото. Telegram разбивает 30 фото на альбомы по 10
    и подпись ставит только к первому — остальные приходят без неё.
    Поэтому пачка без подписи берёт хэштег предыдущей, если та была
    совсем недавно.
    """
    if caption_tag:
        return caption_tag

    if last and now - last[1] <= ttl:
        return last[0]

    return None


# Фразы для коллекций-действий: предмет стоит после двоеточия,
# поэтому его не нужно склонять — «Стас отправил Кате: булочка»
LIBRARY_PHRASES = (
    "{emoji} {actor} <отправил|отправила> {target_dat}: <b>{item}</b>",
    "{emoji} {actor} <поделился|поделилась> с {target_instr}: <b>{item}</b>",
    "{emoji} Для {target_gen} от {actor_gen}: <b>{item}</b>",
    "{emoji} {target}, это тебе от {actor_gen}: <b>{item}</b>",
)


def stem(word: str) -> str:
    """«булочка» → «булочк»: ловит «булочку», «булочки», «булочкой»."""
    word = normalize_tag(word) or ""
    if " " in word or len(word) < 5:
        return word
    return re.sub(r"[аяоеиыуюь]$", "", word) or word


def trigger_matches(text: str, triggers: list[str]) -> bool:
    """
    Короткое сообщение (до 3 слов), которое начинается со слова-триггера
    в любой форме. Длинные фразы не считаются — иначе действие
    срабатывало бы посреди разговора.
    """
    clean = normalize_tag(re.sub(r"@\w+", " ", text or "")) or ""

    if not clean or len(clean.split()) > 3:
        return False

    for trigger in triggers:
        base = stem(trigger)
        if base and (clean == normalize_tag(trigger) or clean.startswith(base)):
            return True

    return False


def guess_target(tag: str) -> str | None:
    """К чему привязать коллекцию автоматически."""
    if tag in CAT_WORDS:
        return CATS

    if tag in PAIR_WORDS:
        return PAIR

    from actions.catalog import find_action

    action = find_action(tag)
    return action.key if action else None


# ---------------------------------------------------------
# Привязки: коллекция ↔ действие
# ---------------------------------------------------------

_tags_for: dict[str, list[str]] = {}     # действие/cats → коллекции
_collections: dict[str, dict] = {}       # тег → настройки коллекции-действия


def prime_links(pairs) -> None:
    result: dict[str, list[str]] = {}
    for tag, target in pairs:
        result.setdefault(target, []).append(tag)
    _tags_for.clear()
    _tags_for.update(result)


async def reload_links() -> None:
    from database.repository import all_library_links

    prime_links(await all_library_links())


def tags_for(target: str) -> list[str]:
    # Своё действие коллекции: ключ «lib:булочка» → коллекция «булочка»
    if target.startswith("lib:"):
        return [target[4:]]
    return _tags_for.get(target, [])


def prime_collections(rows) -> None:
    _collections.clear()
    for row in rows:
        _collections[row.tag] = {
            "emoji": row.emoji or "✨",
            "as_action": bool(row.as_action),
            "triggers": list(row.triggers or []),
            "phrase": row.phrase,
        }


async def reload_collections() -> None:
    from database.repository import list_library_collections

    prime_collections(await list_library_collections())


def action_for(tag: str):
    """Коллекция в виде действия — тем же объектом, что и встроенные."""
    from actions.catalog_data import Action

    meta = _collections.get(tag, {})

    return Action(
        key=f"lib:{tag}",
        emoji=meta.get("emoji") or "✨",
        search=tag,
        aliases=tuple([tag] + meta.get("triggers", [])),
        category="library",
        item_acc=tag,
        item_instr=tag,
    )


def find_collection_action(text: str):
    """Своё действие по тексту сообщения — или None."""
    for tag, meta in _collections.items():
        if meta.get("as_action") and trigger_matches(text, [tag] + meta.get("triggers", [])):
            return action_for(tag)
    return None


def phrases_for(action) -> tuple:
    tag = action.key[4:] if action.key.startswith("lib:") else action.key
    own = (_collections.get(tag) or {}).get("phrase")
    return (own,) if own else LIBRARY_PHRASES


async def pick(chat_id: int | None, target: str) -> dict | None:
    """Картинка из своих коллекций для действия — или None."""
    if chat_id is not None and chat_id < 0 and not is_enabled(chat_id, "library"):
        return None

    tags = tags_for(target)

    if not tags:
        return None

    from database.repository import pick_library_image

    try:
        return await pick_library_image(tags)
    except Exception as error:
        logger.error("LIBRARY PICK: %s %s", type(error).__name__, error)
        return None
