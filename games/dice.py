"""
Кубики, монетка и рандомайзер.

Мелочи, которые дают повод собраться: бросить кубик, подкинуть
монетку, выбрать, кто идёт за пивом.

Формат броска — привычный настольщикам: 2d6, 3d20+5.
"""

import logging
import random
import re
from html import escape

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from botcontext import display_name_of

from settings.store import is_enabled


logger = logging.getLogger("maruska.dice")

router = Router(name="dice")


from games.dice_core import (
    DICE_RE,
    EIGHT_BALL,
    FACES,
    MAX_DICE,
    MAX_SIDES,
    parse_roll,
    roll,
)


COIN_SIDES = (("🪙", "Орёл"), ("🪙", "Решка"))


def games_on(message: Message) -> bool:
    return is_enabled(message.chat.id, "games")


def format_roll(name: str, count: int, sides: int, modifier: int) -> str:
    values = roll(count, sides)
    total = sum(values) + modifier

    if sides == 6:
        shown = " ".join(FACES.get(value, str(value)) for value in values)
    else:
        shown = " ".join(str(value) for value in values)

    lines = [f"🎲 <b>{name}</b> бросает {count}d{sides}"]

    if modifier:
        lines[0] += f"{modifier:+d}"

    lines.append(f"\n{shown}")

    if count > 1 or modifier:
        lines.append(f"\nИтого: <b>{total}</b>")

    # Краевые случаи стоит отметить отдельно
    if count == 1 and sides == 20:
        if values[0] == 20:
            lines.append("\n💥 Критический успех!")
        elif values[0] == 1:
            lines.append("\n💀 Критический провал.")

    elif count > 1 and all(value == sides for value in values):
        lines.append("\n🔥 Все максимальные. Так не бывает.")

    return "".join(lines)


@router.message(Command("dice", "roll", "d"))
async def dice_command(message: Message):
    if not games_on(message):
        await message.reply("🎲 Игры в этой группе выключены (/settings).")
        return

    parts = (message.text or "").split(maxsplit=1)
    argument = parts[1] if len(parts) > 1 else "1d6"

    parsed = parse_roll(argument)

    if parsed is None:
        await message.reply(
            "🎲 Не поняла бросок.\n\n"
            "Примеры: <code>/dice</code>, <code>/dice 2d6</code>, "
            "<code>/dice 3d20+5</code>\n"
            f"Максимум {MAX_DICE} кубиков по {MAX_SIDES} граней."
        )
        return

    count, sides, modifier = parsed

    await message.answer(
        format_roll(
            escape(display_name_of(message.from_user)),
            count,
            sides,
            modifier,
        )
    )


@router.message(Command("coin", "flip"))
async def coin_command(message: Message):
    if not games_on(message):
        await message.reply("🎲 Игры в этой группе выключены (/settings).")
        return

    emoji, side = random.choice(COIN_SIDES)

    await message.answer(
        f"{emoji} <b>{escape(display_name_of(message.from_user))}</b> "
        f"подбрасывает монетку…\n\nВыпал <b>{side}</b>"
    )


@router.message(Command("random", "choose", "pick"))
async def random_command(message: Message):
    """
    /random 1 100        — число в диапазоне
    /random чай кофе пиво — выбор из списка
    """
    if not games_on(message):
        await message.reply("🎲 Игры в этой группе выключены (/settings).")
        return

    parts = (message.text or "").split(maxsplit=1)
    argument = parts[1].strip() if len(parts) > 1 else ""

    name = escape(display_name_of(message.from_user))

    if not argument:
        value = random.randint(1, 100)
        await message.answer(f"🎯 <b>{name}</b> получает: <b>{value}</b>")
        return

    # Вариант «диапазон»: два числа
    numbers = argument.replace("-", " ").split()

    if len(numbers) == 2 and all(n.lstrip("+").isdigit() for n in numbers):
        low, high = sorted(int(n) for n in numbers)
        value = random.randint(low, high)

        await message.answer(
            f"🎯 <b>{name}</b> бросает от {low} до {high}: <b>{value}</b>"
        )
        return

    # Вариант «выбор»: по запятым или по словам
    if "," in argument:
        options = [part.strip() for part in argument.split(",")]
    else:
        options = argument.split()

    options = [option for option in options if option][:20]

    if len(options) < 2:
        await message.reply(
            "🎯 Дай хотя бы два варианта:\n"
            "<code>/random чай, кофе, пиво</code>\n"
            "или диапазон: <code>/random 1 100</code>"
        )
        return

    choice = random.choice(options)

    await message.answer(
        f"🎯 <b>{name}</b> спрашивает, а я отвечаю:\n\n"
        f"<b>{escape(choice)}</b>"
    )


@router.message(Command("8ball", "ball", "shar"))
async def eight_ball(message: Message):
    if not games_on(message):
        await message.reply("🎲 Игры в этой группе выключены (/settings).")
        return

    parts = (message.text or "").split(maxsplit=1)

    if len(parts) < 2:
        await message.reply(
            "🎱 Задай вопрос: <code>/8ball пойдём в пятницу?</code>"
        )
        return

    answer = random.choice(EIGHT_BALL)

    await message.answer(
        f"🎱 <i>{escape(parts[1][:200])}</i>\n\n<b>{answer}</b>"
    )
