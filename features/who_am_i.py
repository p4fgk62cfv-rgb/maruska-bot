"""
«Мара, кто я?» — Мара рассказывает о человеке по памяти.

Берёт его последние сообщения в этой группе (их Мара хранит все, если
память включена) и то, что знает сама: сколько он в группе и сколько
написал, день рождения, брак, карму. Из этого нейросеть пишет короткую
дружескую характеристику с юмором — без выдумок.

    Мара, кто я? / кто я такой? / что ты обо мне знаешь? / расскажи обо мне
    Мара, кто @ник? / ответом на сообщение: «Мара, кто это?»

«Мара, кто я сегодня?» — это уже «кто сегодня» (случайный участник).
"""

import logging
import re
from datetime import datetime
from html import escape

from aiogram import Router
from aiogram.types import Message

import botcontext
from botcontext import TRIGGER_RE, display_name_of, is_addressed
from settings.store import get_value, is_enabled


logger = logging.getLogger("maruska.who_am_i")

router = Router(name="who_am_i")

MESSAGES = 60
MIN_MESSAGES = 3

_ABOUT_ME = re.compile(
    r"^\W*(?:кто\s+я(?:\s+так(?:ой|ая))?|что\s+ты\s+(?:знаешь\s+)?обо\s+мне(?:\s+знаешь)?|расскажи\s+обо\s+мне"
    r"|какой\s+я|какая\s+я)\W*$",
    re.IGNORECASE,
)
_ABOUT_OTHER = re.compile(r"^\W*кто\s+(?:это|он|она|так(?:ой|ая))(?:\s+так(?:ой|ая))?\W*$", re.IGNORECASE)
_ABOUT_MENTION = re.compile(r"^\W*(?:кто|что\s+знаешь\s+(?:о|про))\s+(?:так(?:ой|ая)\s+)?@(\w{4,32})\W*$", re.IGNORECASE)

PROMPT = (
    "Ты — Маруська, весёлая участница группового чата. Тебя спросили: «{question}».\n"
    "Расскажи о человеке «{name}» в 3–5 предложениях: какой он в чате, о чём любит говорить, "
    "какие словечки и привычки заметны. Дружелюбно, с лёгким юмором, обращайся {address}.\n"
    "Правила: опирайся ТОЛЬКО на факты и сообщения ниже, ничего не выдумывай; не пересказывай "
    "сообщения дословно; не упоминай здоровье, адреса, телефоны и другую личную информацию; "
    "без оскорблений. Отвечай простым текстом без разметки.\n\n"
    "Что знает Маруська:\n{facts}\n\n"
    "Его последние сообщения в чате (от старых к новым):\n{messages}"
)


def parse(message: Message) -> tuple[str, str | None] | None:
    """('me' | 'reply' | 'mention', @ник) или None, если это не такой вопрос."""
    text = message.text or ""
    if not text or text.startswith("/"):
        return None
    body = TRIGGER_RE.sub(" ", text, count=1).replace(",", " ")
    if _ABOUT_ME.match(body):
        return "me", None
    found = _ABOUT_MENTION.match(body)
    if found:
        return "mention", found.group(1)
    reply = message.reply_to_message
    if _ABOUT_OTHER.match(body) and reply and reply.from_user and not reply.from_user.is_bot:
        return "reply", None
    return None


def is_who_am_i(message: Message) -> bool:
    if message.chat.type not in ("group", "supergroup"):
        return False
    if message.from_user is None or message.from_user.is_bot:
        return False
    if not is_enabled(message.chat.id, "ai"):
        return False
    return parse(message) is not None and is_addressed(message)


def _days(moment: datetime | None) -> int | None:
    if moment is None:
        return None
    return max(0, (datetime.utcnow() - moment.replace(tzinfo=None)).days)


async def collect_facts(chat_id: int, telegram_id: int) -> list[str]:
    from database.repository import (
        active_marriage,
        get_birthday,
        get_member,
        get_profile,
        groups_count,
        member_name,
        member_since,
    )

    facts = []
    member = await get_member(chat_id, telegram_id)
    if member is not None and member.messages_count:
        facts.append(f"Написал в этой группе сообщений: {member.messages_count}")
    since = await member_since(chat_id, telegram_id)
    days = _days(since["joined_at"]) if since else None
    if days is not None:
        facts.append(f"В группе дней: {days}")
    profile = await get_profile(telegram_id)
    # Дальше — про человека целиком, из всех групп с Марой
    groups = await groups_count(telegram_id)
    if groups > 1:
        facts.append(f"Состоит в группах с Марой: {groups}")
    total = getattr(profile, "messages_count", 0) or 0
    if total and groups > 1:
        facts.append(f"Всего сообщений во всех группах: {total}")
    if getattr(profile, "games_played", 0):
        facts.append(f"Сыграно игр: {profile.games_played}, побед: {profile.games_won or 0}")
    if profile is not None and profile.karma:
        facts.append(f"Карма (рейтинг от других): {profile.karma}")
    if getattr(profile, "xp", 0) and is_enabled(chat_id, "progress"):
        from progress.xp import level_from_xp

        facts.append(f"Уровень: {level_from_xp(profile.xp)}")
    if is_enabled(chat_id, "economy"):
        try:
            from database.repository import get_balance
            from economy.service import money

            balance = await get_balance(telegram_id)
            if balance:
                facts.append(f"Алмазов: {money(balance)}")
        except Exception:
            pass
    birthday = await get_birthday(telegram_id)
    if birthday:
        facts.append(f"День рождения: {birthday[0]:02d}.{birthday[1]:02d}")
    marriage = await active_marriage(chat_id, telegram_id)
    if marriage is not None:
        partner = marriage.user2 if marriage.user1 == telegram_id else marriage.user1
        days = max((datetime.utcnow() - marriage.since).days, 0) + 1
        facts.append(f"В браке с: {await member_name(chat_id, partner)} (вместе {days} дн.)")
    return facts


def _fallback(name: str, facts: list[str]) -> str:
    lines = "\n".join(f"• {escape(f)}" for f in facts) or "• пока почти ничего 🙈"
    return f"🔮 Вот что Маруська знает про <b>{escape(name)}</b>:\n{lines}"


async def _resolve(message: Message, kind: str, username: str | None):
    """Про кого спрашивают: (id, имя) или None."""
    if kind == "me":
        return message.from_user.id, display_name_of(message.from_user)
    if kind == "reply":
        target = message.reply_to_message.from_user
        return target.id, display_name_of(target)
    from database.repository import get_user_by_username, member_name

    user = await get_user_by_username(username)
    if user is None:
        return None
    return user.telegram_id, await member_name(message.chat.id, user.telegram_id)


@router.message(is_who_am_i)
async def who_am_i(message: Message):
    kind, username = parse(message)
    await describe(message, kind, username)


async def describe(message: Message, kind: str, username: str | None = None, question: str | None = None):
    """Рассказ о человеке: «Мара, кто я?», «Мара, кто это?» ответом, «Мара, кто @ник?» и /profile."""
    from ai.router import ask_ai
    from database.repository import user_messages, user_messages_elsewhere

    target = await _resolve(message, kind, username)
    if target is None:
        await message.reply(f"🤷 Не знаю такого: @{escape(username or '')}. Пусть сначала напишет в чат.")
        return
    telegram_id, name = target
    if telegram_id == botcontext.BOT_ID:
        await message.reply("🔮 Это я, Маруська. Самая умная и скромная в этом чате 😌")
        return

    chat_id = message.chat.id
    messages = await user_messages(chat_id, telegram_id, MESSAGES)
    # В новой группе человек почти не писал — добираем из других групп с Марой
    if len(messages) < MESSAGES:
        messages = await user_messages_elsewhere(chat_id, telegram_id, MESSAGES - len(messages)) + messages
    messages = [m for m in messages if m and not m.startswith("/")]
    facts = await collect_facts(chat_id, telegram_id)
    about_self = telegram_id == message.from_user.id

    if len(messages) < MIN_MESSAGES:
        who = "тебя" if about_self else f"<b>{escape(name)}</b>"
        await message.reply(
            f"🔮 Я пока мало знаю про {who} — в памяти почти нет сообщений. "
            "Пообщаемся побольше — расскажу всё 😉"
            + ("\n\n" + _fallback(name, facts) if facts else "")
        )
        return

    try:
        await message.bot.send_chat_action(chat_id, "typing")
    except Exception:
        pass

    prompt = PROMPT.format(
        question=(question or message.text or "")[:100],
        name=name,
        address="к нему на «ты»" if about_self else "к спросившему, говоря о человеке в третьем лице",
        facts="\n".join(f"- {f}" for f in facts) or "- ничего особенного",
        messages="\n".join(f"- {m[:300]}" for m in messages),
    )
    try:
        answer = await ask_ai(prompt, persona=get_value(chat_id, "persona"))
    except Exception as error:
        logger.warning("WHO AM I: %s %s", type(error).__name__, error)
        answer = ""

    if not answer:
        await message.reply(_fallback(name, facts))
        return
    await message.reply(f"🔮 {escape(answer)}")
