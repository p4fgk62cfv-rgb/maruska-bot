"""
«Гармония» — насколько гармоничны отношения двоих.

Ответом на сообщение человека или с его @ником:
    «гармония», «гармония @kate», /harmony

    Аня + Вася
    Гармоничность ваших отношений составляет 65,7%
    и под этим — тёплая или колкая фраза Мары: чем выше процент, тем теплее.

Процент на день постоянный для пары: спросить ещё раз можно, но
перебором до 100% не выйдет. Завтра — новый расклад.
"""

import hashlib
import random
import re
from html import escape

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from botcontext import display_name_of
from settings.store import is_enabled, local_now


router = Router(name="harmony")

HARMONY_RE = re.compile(r"^\s*/?\s*гармони[яюиейё]\b[\s,!?.]*(@\w+)?[\s!?.]*$", re.IGNORECASE)

# Нижняя граница → фразы. Чем выше процент, тем теплее.
TIERS = (
    (95, (
        "Я думаю, вам пора уединиться 🔥",
        "Вы не думали подавать заявление в ЗАГС? 💍",
        "Это не гармония, это судьба. Мара уже плачет от умиления 🥹",
        "Даже звёзды на небе выстроились в ваши инициалы ✨",
        "Таких пар не бывает. Хотя вот же вы 💞",
        "Можно я буду свидетельницей на свадьбе? 👰",
    )),
    (85, (
        "Ещё чуть-чуть — и Мара начнёт выбирать платье на вашу свадьбу 👗",
        "Вы как чай с лимоном: по отдельности хорошо, а вместе — уют ☕🍋",
        "Тут даже Купидону делать нечего — всё уже случилось 💘",
        "Кажется, кто-то в этом чате влюблён. И это взаимно 😏",
        "Такая гармония бывает только у кофе с утром ☀️",
    )),
    (70, (
        "Очень тепло. Если позовёте друг друга на чай — Мара одобряет ☕",
        "Хорошая пара! Осталось только кому-то сделать первый шаг 👣",
        "Между вами искрит. Мара видит, Мара всё видит 👀",
        "Вы бы точно не поругались, кто моет посуду 🍽",
        "Гармония на уровне «доедать друг за другом картошку фри» 🍟",
    )),
    (55, (
        "Вполне неплохо! Есть над чем работать, но фундамент крепкий 🧱",
        "Вы как Wi-Fi в кафе: связь есть, но иногда пропадает 📶",
        "Дружба точно получится, а дальше — как карта ляжет 🃏",
        "Совместимость средняя, но с шоколадкой можно поднять до 80% 🍫",
        "Мара в вас верит. Немного. Процентов на шестьдесят 🤞",
    )),
    (40, (
        "Ну… бывает и хуже. Например, у кошки с пылесосом 🐈🧹",
        "Вам бы для начала договориться, какой сериал смотреть 📺",
        "Это как ананас на пицце: кому-то нравится, кому-то нет 🍍",
        "Совместимость «вместе только в пробке» 🚗",
        "Гармония есть, но она пока стесняется и прячется 🙈",
    )),
    (25, (
        "Мара бы не советовала делить с вами одну пиццу 🍕",
        "Вы как кот и огурец: встреча неожиданная, реакция бурная 🥒",
        "Скорее соседи по лестничной клетке, чем пара 🚪",
        "Тут нужна не гармония, а переговорщик ООН 🕊",
        "Лучше общаться через Мару. Она передаст 📨",
    )),
    (10, (
        "Ой. Может, просто останемся знакомыми? 😬",
        "Вы как вилка и розетка: лучше не соединять ⚡",
        "Совместимость уровня «спор о том, где у батона попка» 🥖",
        "Звёзды сказали «нет», а потом ещё раз «нет» 🌌",
        "Мара уже прячет посуду, чтобы вы не начали ей кидаться 🍽",
    )),
    (0, (
        "Это не отношения, это холодная война ❄️",
        "Даже Мара не знает, как вас примирить. А она знает всё 🤷‍♀️",
        "Держитесь друг от друга на расстоянии вытянутой клавиатуры ⌨️",
        "Если вы когда-нибудь договоритесь — это будет чудо года 🎆",
        "Гармония ушла за хлебом и не вернулась 🍞",
    )),
)

SELF_PHRASES = (
    "Гармония с самим собой — 100%. Мара гордится 🧘",
    "Себя любить — это правильно. Но попробуй ответить кому-нибудь другому 😉",
)

MARA_PHRASES = (
    "Со мной у всех гармония 100%. Я же Мара 💜",
    "Я бот, у меня гармония только с сервером. Но с тобой — почти так же 🤖💞",
)


def is_harmony_request(text: str | None) -> bool:
    return bool(text) and HARMONY_RE.match(text) is not None


def harmony_percent(chat_id: int, user_a: int, user_b: int, day: str) -> float:
    """Процент пары на день: 0.0–100.0 с одним знаком. Порядок двоих не важен."""
    low, high = sorted((user_a, user_b))
    digest = hashlib.sha256(f"{chat_id}:{low}:{high}:{day}".encode()).digest()
    return int.from_bytes(digest[:4], "big") % 1001 / 10


def comment_for(percent: float, rng=random) -> str:
    for floor, phrases in TIERS:
        if percent >= floor:
            return rng.choice(phrases)
    return rng.choice(TIERS[-1][1])


def hearts(percent: float) -> str:
    full = round(percent / 10)
    return "❤️" * full + "🤍" * (10 - full)


def format_harmony(name_a: str, name_b: str, percent: float, rng=random) -> str:
    value = f"{percent:.1f}".replace(".", ",")
    return (
        f"💞 <b>{escape(name_a)}</b> + <b>{escape(name_b)}</b>\n"
        f"Гармоничность ваших отношений составляет <b>{value}%</b>\n"
        f"{hearts(percent)}\n\n"
        f"{comment_for(percent, rng)}"
    )


async def _harmony(message: Message) -> None:
    if message.chat.type not in ("group", "supergroup") or not message.from_user:
        return

    if not is_enabled(message.chat.id, "harmony"):
        return

    from features.moderation import _target_of

    me = message.from_user
    reply = message.reply_to_message
    bot_me = await message.bot.me()

    if reply is not None and reply.from_user is not None and reply.from_user.id == bot_me.id:
        await message.reply(random.choice(MARA_PHRASES))
        return

    target = await _target_of(message)

    if target is None:
        await message.reply("💞 Ответь «гармония» на сообщение человека или напиши <code>гармония @ник</code>.")
        return

    if target.id == me.id:
        await message.reply(random.choice(SELF_PHRASES))
        return

    day = local_now(message.chat.id).strftime("%Y-%m-%d")
    percent = harmony_percent(message.chat.id, me.id, target.id, day)

    await message.reply(format_harmony(display_name_of(me), display_name_of(target), percent))


@router.message(Command("harmony", "гармония", ignore_case=True))
async def harmony_command(message: Message):
    await _harmony(message)


@router.message(lambda m: m.chat.type in ("group", "supergroup") and is_harmony_request(m.text))
async def harmony_text(message: Message):
    await _harmony(message)
