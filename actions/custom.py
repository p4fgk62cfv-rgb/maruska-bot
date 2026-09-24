"""
Правки действий для группы — слой поверх встроенного каталога.

Встроенный каталог (actions/catalog.py, actions/phrases.py) остаётся
основой. Поверх него у каждой группы в базе могут быть:
    свои слова-триггеры, свои фразы, свои картинки,
    скрытые картинки общей коллекции, задержка между срабатываниями.

Всё держится в памяти рядом с настройками группы — проверка в
фильтре сообщений не ходит в базу.
"""

import random
import re
import time
from dataclasses import dataclass, field

from actions.catalog import ACTIONS


ACTION_BY_KEY = {action.key: action for action in ACTIONS}

# Какие подстановки можно использовать в своих фразах
PLACEHOLDERS = {
    "emoji": "эмодзи действия",
    "actor": "кто сделал",
    "actor_gen": "кого (кто сделал)",
    "actor_dat": "кому (кто сделал)",
    "target": "кому адресовано",
    "target_acc": "кого (адресат)",
    "target_dat": "кому (адресат)",
    "target_gen": "кого/чего (адресат)",
    "target_instr": "кем (адресат)",
    "item": "предмет: пиво, розу…",
    "item_instr": "чем: пивом, розой…",
}

ALLOWED_TAGS = {"b", "i", "u", "s"}

MAX_ALIAS = 40
MAX_PHRASE = 300
MAX_UPLOAD = 2 * 1024 * 1024


@dataclass
class ChatCustom:
    aliases: dict[str, str] = field(default_factory=dict)          # слово -> ключ действия
    phrases: dict[str, list[str]] = field(default_factory=dict)     # ключ -> шаблоны
    images: dict[str, list[dict]] = field(default_factory=dict)     # ключ -> [{id, value, file_id}]
    hidden: set[int] = field(default_factory=set)                   # id картинок общей коллекции
    cooldown: dict[str, int] = field(default_factory=dict)          # ключ -> секунд
    image_mode: dict[str, str] = field(default_factory=dict)        # ключ -> mix | own
    hidden_aliases: dict[str, set] = field(default_factory=dict)    # ключ -> встроенные слова
    hidden_phrases: set[str] = field(default_factory=set)           # встроенные фразы


_cache: dict[int, ChatCustom] = {}
_last_used: dict[tuple[int, str], float] = {}


# ---------------------------------------------------------
# Чистые функции — покрыты тестами
# ---------------------------------------------------------

def normalize_alias(text: str) -> str:
    """«Пивка!!» → «пивка», «@kate обнять» → «обнять»."""
    cleaned = re.sub(r"@\w+", " ", (text or "").lower().replace("ё", "е"))
    cleaned = re.sub(r"[^\w\s-]", " ", cleaned)
    return " ".join(cleaned.split())


def validate_alias(text: str) -> str | None:
    alias = normalize_alias(text)

    if len(alias) < 2:
        return "Слишком коротко — нужно хотя бы 2 буквы"

    if len(alias) > MAX_ALIAS:
        return f"Слишком длинно — максимум {MAX_ALIAS} символов"

    if len(alias.split()) > 3:
        return "Действие — это 1–3 слова, а не предложение"

    return None


SAMPLE = {
    "emoji": "🍺", "actor": "Стас", "actor_gen": "Стаса", "actor_dat": "Стасу",
    "target": "Катя", "target_acc": "Катю", "target_dat": "Кате",
    "target_gen": "Кати", "target_instr": "Катей",
    "item": "пиво", "item_instr": "пивом",
}


def validate_phrase(template: str) -> str | None:
    """
    Проверяет свою фразу до сохранения: неизвестная подстановка
    сломала бы отправку действия в чате.
    """
    from actions.phrases import render

    text = (template or "").strip()

    if len(text) < 5:
        return "Фраза слишком короткая"

    if len(text) > MAX_PHRASE:
        return f"Фраза длиннее {MAX_PHRASE} символов"

    if "{actor}" not in text and "{target" not in text:
        return "Во фразе нужен хотя бы {actor} или {target} — иначе непонятно, кто кого"

    # Telegram разбирает подпись как HTML: чужой тег или голый «&»
    # сломают отправку действия, а в панели — дадут внедрить код
    tags = {tag.lower() for tag in re.findall(r"</?([a-zA-Z][\w-]*)", text)}

    if tags - ALLOWED_TAGS:
        return "Из тегов можно только <b>, <i>, <u>, <s> — остальное Telegram не примет"

    if re.search(r"&(?![a-z]+;|#\d+;)", text):
        return "Символ «&» нельзя — напиши «и»"

    unknown = set(re.findall(r"\{(\w+)\}", text)) - set(PLACEHOLDERS)

    if unknown:
        return "Непонятные подстановки: " + ", ".join("{" + u + "}" for u in sorted(unknown))

    try:
        render(text, "male", **SAMPLE)
        render(text, "female", **SAMPLE)
    except (KeyError, IndexError, ValueError):
        return "Фраза не собирается — проверь фигурные скобки и <он|она>"

    return None


def preview_phrase(template: str, gender: str = "male", **names) -> str:
    from actions.phrases import render

    values = dict(SAMPLE, **names)
    return render(template, gender, **values)


# ---------------------------------------------------------
# Кэш группы
# ---------------------------------------------------------

def prime(chat_id: int, rows) -> None:
    custom = ChatCustom()

    for row in rows:
        key = row.action_key

        if key not in ACTION_BY_KEY:
            continue

        if row.kind == "alias":
            custom.aliases[normalize_alias(row.value)] = key
        elif row.kind == "phrase":
            custom.phrases.setdefault(key, []).append(row.value)
        elif row.kind == "image":
            custom.images.setdefault(key, []).append(
                {"id": row.id, "value": row.value, "file_id": row.file_id}
            )
        elif row.kind == "hide_image":
            try:
                custom.hidden.add(int(row.value))
            except ValueError:
                pass
        elif row.kind == "cooldown":
            try:
                custom.cooldown[key] = max(0, int(row.value))
            except ValueError:
                pass
        elif row.kind == "hide_alias":
            custom.hidden_aliases.setdefault(key, set()).add(row.value)
        elif row.kind == "hide_phrase":
            custom.hidden_phrases.add(row.value)
        elif row.kind == "image_mode":
            custom.image_mode[key] = row.value if row.value in ("mix", "own") else "mix"

    _cache[chat_id] = custom


def is_loaded(chat_id: int) -> bool:
    return chat_id in _cache


def get(chat_id: int | None) -> ChatCustom:
    if chat_id is None:
        return ChatCustom()
    return _cache.get(chat_id) or ChatCustom()


async def reload(chat_id: int) -> None:
    from database.repository import list_action_custom

    prime(chat_id, await list_action_custom(chat_id))


def forget(chat_id: int) -> None:
    _cache.pop(chat_id, None)


# ---------------------------------------------------------
# Использование в обработчике
# ---------------------------------------------------------

def resolve(chat_id: int | None, text: str | None):
    """
    Действие по тексту: сначала встроенный каталог, потом свои
    слова группы.
    """
    from actions.catalog import find_action

    hidden = get(chat_id).hidden_aliases if chat_id is not None else None
    found = find_action(text, hidden=hidden)

    if found is not None:
        return found

    if chat_id is None or not text or text.strip().startswith("/"):
        return None

    key = get(chat_id).aliases.get(normalize_alias(text))

    return ACTION_BY_KEY.get(key) if key else None


def pick_custom_phrase(chat_id: int, key: str, builtin_count: int = 10) -> str | None:
    """
    Своя фраза с вероятностью, пропорциональной их числу: одна своя
    фраза среди десяти встроенных не должна выпадать через раз.
    """
    customs = get(chat_id).phrases.get(key) or []

    if not customs:
        return None

    if random.random() < len(customs) / (len(customs) + builtin_count):
        return random.choice(customs)

    return None


def pick_phrase(chat_id: int, action) -> str:
    """Своя фраза группы или встроенная — но не скрытая в группе."""
    from actions.phrases import pick_template

    own = pick_custom_phrase(chat_id, action.key)

    return own or pick_template(action, hidden=get(chat_id).hidden_phrases)


def pick_custom_image(chat_id: int, key: str) -> dict | None:
    custom = get(chat_id)
    images = custom.images.get(key) or []

    if not images:
        return None

    if custom.image_mode.get(key) == "own" or random.random() < 0.5:
        return random.choice(images)

    return None


def only_own_images(chat_id: int, key: str) -> bool:
    custom = get(chat_id)
    return custom.image_mode.get(key) == "own" and bool(custom.images.get(key))


def is_hidden(chat_id: int, image_id: int | None) -> bool:
    return image_id is not None and image_id in get(chat_id).hidden


def cooling_down(chat_id: int, key: str) -> bool:
    seconds = get(chat_id).cooldown.get(key, 0)

    if not seconds:
        return False

    last = _last_used.get((chat_id, key))

    return last is not None and time.monotonic() - last < seconds


def mark_used(chat_id: int, key: str) -> None:
    _last_used[(chat_id, key)] = time.monotonic()
