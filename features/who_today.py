"""
«Мара, кто сегодня …» — Мара выбирает случайного участника группы.

    Мара, кто сегодня улитка?          → «Катя сегодня улитка 🐌»
    Мара, кто меня сегодня любит?      → «Стас, сегодня тебя любит — Катя 💘»
    Мара, кто сегодня моя зайка?       → «Стас, сегодня твоя зайка — Катя»

Нужно обращение к Маре и оба слова — «кто» и «сегодня»: так «Мара, кто
я?» и «Мара, кто такой Пушкин» по-прежнему уходят нейросети. Каждый раз
новый человек — спрашивать можно сколько угодно.
"""

import random
import re
from html import escape

from aiogram import Router
from aiogram.types import Message

from botcontext import TRIGGER_RE, display_name_of, is_addressed
from settings.store import is_enabled


router = Router(name="who_today")

ACTIVE_DAYS = 30
MAX_WORDS = 7

_WHO = re.compile(r"(?<![а-яё])кто(?![а-яё])", re.IGNORECASE)
_TODAY = re.compile(r"(?<![а-яё])(?:сегодня|седня|сёдня)(?![а-яё])", re.IGNORECASE)
# Слова, которые в ответе не нужны: «кто у нас в чате сегодня …»
_FILLER = re.compile(r"(?<![а-яё])(?:кто|сегодня|седня|сёдня|у нас|в чате|в группе|тут|здесь|же|ну)(?![а-яё])", re.IGNORECASE)

# «я» спрашивающего → «ты» в ответе
FIRST_PERSON = {
    "я": "ты", "меня": "тебя", "мне": "тебе", "мной": "тобой", "мною": "тобою",
    "мой": "твой", "моя": "твоя", "моё": "твоё", "мое": "твое", "мои": "твои",
    "моего": "твоего", "моей": "твоей", "моему": "твоему", "моим": "твоим", "моих": "твоих", "мою": "твою",
}

EMOJIS = ("✨", "🎯", "🔮", "👀", "🎲", "😏", "🌟", "🥁")

ABOUT_ASKER = (
    "{emoji} {asker}, сегодня {rest} — {who}",
    "{emoji} Звёзды сошлись: {asker}, сегодня {rest} — {who}",
    "{emoji} {asker}, Маруська всё знает: сегодня {rest} — {who}",
    "{emoji} {asker}, без вариантов: сегодня {rest} — {who}",
)

ABOUT_SOMEONE = (
    "{emoji} {who} сегодня {rest}",
    "{emoji} Маруська проверила: {who} сегодня {rest}",
    "{emoji} Сегодня {rest} — {who}. Решение окончательное",
    "{emoji} Барабанная дробь… {who} сегодня {rest}!",
    "{emoji} Тут и думать нечего: {who} сегодня {rest}",
)


def mention(user_id: int, name: str) -> str:
    return f'<a href="tg://user?id={user_id}">{escape(name)}</a>'


def parse(text: str | None) -> tuple[str, bool] | None:
    """«Мара, кто меня сегодня любит?» → («тебя любит», True). Не тот вопрос — None."""
    if not text or text.startswith("/"):
        return None
    body = TRIGGER_RE.sub(" ", text, count=1)
    if not _WHO.search(body) or not _TODAY.search(body):
        return None
    body = _FILLER.sub(" ", body)
    words = re.findall(r"[а-яёa-z0-9-]+", body.lower())
    if not words or len(words) > MAX_WORDS:
        return None
    personal = any(w in FIRST_PERSON for w in words)
    rest = " ".join(FIRST_PERSON.get(w, w) for w in words)
    return rest, personal


def is_who_question(message: Message) -> bool:
    if message.chat.type not in ("group", "supergroup"):
        return False
    if message.from_user is None or message.from_user.is_bot:
        return False
    if not is_enabled(message.chat.id, "who_today"):
        return False
    return parse(message.text) is not None and is_addressed(message)


@router.message(is_who_question)
async def who_today(message: Message):
    from database.repository import pick_candidates

    rest, personal = parse(message.text)
    user = message.from_user
    me = await message.bot.me()
    exclude = {me.id} | ({user.id} if personal else set())

    people = [p for p in await pick_candidates(message.chat.id, ACTIVE_DAYS) if p["telegram_id"] not in exclude]
    asker = mention(user.id, display_name_of(user))

    if not people:
        await message.reply(f"🤷 {asker}, в чате пока некого выбрать — пусть народ сначала напишет пару сообщений.")
        return

    chosen = random.choice(people)
    who = mention(chosen["telegram_id"], chosen["name"])
    template = random.choice(ABOUT_ASKER if personal else ABOUT_SOMEONE)
    await message.reply(template.format(emoji=random.choice(EMOJIS), asker=asker, who=who, rest=escape(rest)))
