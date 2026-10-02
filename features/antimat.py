"""
Антимат.

Админ вписывает в панели запрещённые слова. За каждое Мара удаляет сообщение
и делает словесное предупреждение («1/3», «2/3», «3/3»). Если в настройках
указан срок мута, на последнем предупреждении человек получает мут на этот
срок автоматически, и счёт начинается заново. Срок 0 — только предупреждения.

Слова в списке:
    сука     — только это слово целиком
    хуй*     — слова, начинающиеся с «хуй» (и с приставками: «нахуй», «захуярить»)
    *пизд*   — «пизд» в любом месте слова

Мат ловится и в маскировке: латиница вместо кириллицы («xуй», «cyka»),
цифры («3»→з, «0»→о), растянутые буквы («хууууй»), буквы через точку,
пробел или звёздочку («х.у.й», «х у й»). Админов — по настройке «Наказывать
и админов» (мут админу Telegram не позволяет: им только предупреждения).
"""

import logging
import re
import time
from html import escape

from aiogram import Router
from aiogram.types import Message

import audit
from botcontext import display_name_of
from settings.store import get_number, get_text, is_enabled

logger = logging.getLogger("maruska.antimat")

router = Router(name="antimat")

# Причина предупреждения — по ней антимат считает только свои предупреждения
REASON = "Мат"

from settings.registry import ANTIMAT_DEFAULT_WORDS as DEFAULT_WORDS  # noqa: E402,F401

# Похожие латинские буквы и цифры → кириллица
LOOKALIKE = str.maketrans({
    "a": "а", "b": "в", "c": "с", "e": "е", "h": "н", "k": "к", "m": "м", "o": "о",
    "p": "р", "t": "т", "x": "х", "y": "у", "u": "и", "3": "з", "0": "о", "6": "б",
    "@": "а", "$": "с", "ё": "е",
})

# Приставки, с которыми мат начинается не с корня: «на-хуй», «за-ебал», «вы-блядок»
PREFIXES = (
    "", "на", "за", "вы", "по", "у", "от", "до", "об", "о", "раз", "рас", "при", "про",
    "пере", "недо", "под", "из", "вз", "с", "съ", "в", "под", "долбо", "ни", "ах",
)

_WORD = re.compile(r"[а-яa-z0-9@$ё]+", re.IGNORECASE)
# Буквы, разделённые точками, пробелами, звёздочками, дефисами: «х.у.й», «х у й»
_SPACED = re.compile(r"(?:(?<![а-яa-zё])[а-яa-zё][\s.*_\-]{1,3}){2,}[а-яa-zё](?![а-яa-zё])", re.IGNORECASE)

_cooldown: dict[tuple[int, int], float] = {}
_admin_cache: dict[tuple[int, int], tuple[float, bool]] = {}


def normalize(word: str) -> str:
    """«XYЙ», «хууууй», «xуй» → «хуй»."""
    word = word.lower().translate(LOOKALIKE)
    word = re.sub(r"[^а-я]", "", word)
    # Растянутые буквы: «хуууй» → «хуй»
    return re.sub(r"(.)\1+", r"\1", word)


def parse_words(raw: str) -> list[str]:
    """Список из панели: через запятую или с новой строки. Звёздочки сохраняются."""
    items = []
    for part in re.split(r"[,\n;]+", raw or ""):
        part = part.strip().lower()
        if not part:
            continue
        head = part.startswith("*")
        tail = part.endswith("*")
        core = normalize(part.strip("*"))
        if len(core) >= 2:
            items.append(("*" if head else "") + core + ("*" if tail else ""))
    return items


def _matches(word: str, entry: str) -> bool:
    if entry.startswith("*") and entry.endswith("*"):
        return entry[1:-1] in word
    if entry.endswith("*"):
        root = entry[:-1]
        return any(word.startswith(p + root) for p in PREFIXES)
    if entry.startswith("*"):
        return word.endswith(entry[1:])
    return word == entry


def tokens(text: str) -> list[str]:
    found = [normalize(w) for w in _WORD.findall(text or "")]
    # «х.у.й», «х у й» — склеиваем буквы
    found += [normalize(m.group(0)) for m in _SPACED.finditer(text or "")]
    return [w for w in found if w]


def find_swear(text: str, words: list[str]) -> str | None:
    """Первое запрещённое слово в тексте или None."""
    if not words:
        return None
    for token in tokens(text):
        for entry in words:
            if _matches(token, entry):
                return token
    return None


def _words(chat_id: int) -> list[str]:
    return parse_words(get_text(chat_id, "antimat_words"))


def is_swearing(message: Message) -> bool:
    if message.chat.type not in ("group", "supergroup"):
        return False
    if message.from_user is None or message.from_user.is_bot:
        return False
    if not is_enabled(message.chat.id, "antimat"):
        return False
    text = message.text or message.caption or ""
    return find_swear(text, _words(message.chat.id)) is not None


async def _is_admin(bot, chat_id: int, user_id: int) -> bool:
    key = (chat_id, user_id)
    cached = _admin_cache.get(key)
    if cached and time.monotonic() - cached[0] < 300:
        return cached[1]
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        admin = member.status in ("creator", "administrator")
    except Exception:
        admin = False
    _admin_cache[key] = (time.monotonic(), admin)
    return admin


@router.message(is_swearing)
async def on_swear(message: Message):
    from database.repository import add_warning, clear_warnings_by_reason, count_warnings_by_reason
    from features.moderation import ModerationError, mute

    chat_id = message.chat.id
    user = message.from_user
    name = display_name_of(user)

    admin = await _is_admin(message.bot, chat_id, user.id)
    if admin and not is_enabled(chat_id, "antimat_admins"):
        return

    if is_enabled(chat_id, "antimat_delete"):
        try:
            await message.delete()
            audit.count(chat_id, "deleted")
        except Exception:
            pass

    # Несколько сообщений подряд за пару секунд — одно предупреждение, не три
    now = time.monotonic()
    key = (chat_id, user.id)
    if now - _cooldown.get(key, 0) < 3:
        return
    _cooldown[key] = now
    if len(_cooldown) > 5000:
        _cooldown.clear()

    limit = max(1, get_number(chat_id, "antimat_warnings") or 3)
    minutes = get_number(chat_id, "antimat_mute_minutes") or 0

    await add_warning(chat_id, user.id, REASON)
    total = await count_warnings_by_reason(chat_id, user.id, REASON)
    audit.count(chat_id, "warnings")
    audit.log(
        "moderation", "warn", chat_id=chat_id, actor_kind="bot",
        target_id=user.id, target_name=name, details=f"{min(total, limit)}/{limit} · мат",
    )

    who = f'<a href="tg://user?id={user.id}">{escape(name)}</a>'

    if total < limit:
        await message.answer(f"🤬 {who}, без мата! Предупреждение {total}/{limit}.")
        return

    # Последнее предупреждение: мут, если админ указал срок; счёт заново
    await clear_warnings_by_reason(chat_id, user.id, REASON)

    if minutes <= 0:
        await message.answer(f"🤬 {who}, без мата! Предупреждение {limit}/{limit}. Следующий раз счёт начнётся заново.")
        return

    try:
        await mute(message.bot, chat_id, user.id, minutes)
    except ModerationError as error:
        logger.warning("ANTIMAT mute: %s", error)
        why = ("Telegram не даёт ограничивать администраторов — только предупреждение."
               if admin else "Замутить не могу — нет права ограничивать участников.")
        await message.answer(f"🤬 {who}, без мата! Предупреждение {limit}/{limit}. {why}")
        return

    audit.count(chat_id, "mutes")
    audit.log(
        "moderation", "mute", chat_id=chat_id, actor_kind="bot",
        target_id=user.id, target_name=name, details=f"{minutes} мин · мат, {limit} предупреждения",
    )
    await message.answer(f"🔇 {who} получает мут на {_duration(minutes)} — {limit} предупреждения за мат.")


def _duration(minutes: int) -> str:
    if minutes % 1440 == 0:
        days = minutes // 1440
        return f"{days} д"
    if minutes % 60 == 0:
        return f"{minutes // 60} ч"
    return f"{minutes} мин"
