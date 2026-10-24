"""
Группа без доступа к функции: Мара не молчит, а один раз объясняет.

Стоит последним: сюда доходит только то, что никто не обработал. Если в группе
открыто не всё (доступ решает владелец — settings/access.py), то на команду,
обращение к Маре («Мара, покажи меня»), слово действия («чай», «кофе») или
«/старт турнир» она отвечает, к кому написать за полным набором функций.
Не чаще раза в 10 минут на группу — чтобы не засорять чат.
"""

import time

from aiogram import F, Router
from aiogram.types import Message

from actions.catalog import find_action
from botcontext import TRIGGER_RE
from settings import access

router = Router(name="locked")

NOTICE = f"🔒 Чтобы пользоваться всеми возможностями Марушки в этой группе, напишите в Telegram {access.CONTACT}"
COOLDOWN = 600
_said: dict[int, float] = {}


def _ours(message: Message) -> bool:
    """Команда без @ или с @ этого бота; «Мара, …» в начале сообщения; слово действия; «покажи меня»."""
    text = (message.text or "").strip()
    lowered = text.lower()
    if find_action(text) is not None or lowered.startswith("покажи ") or lowered.startswith("мяу"):
        return True
    if text.startswith("/"):
        command = text.split()[0]
        if "@" not in command:
            return True
        from botcontext import BOT_USERNAME

        return bool(BOT_USERNAME) and command.lower().endswith("@" + BOT_USERNAME.lower())
    found = TRIGGER_RE.search(text)
    return found is not None and not text[:found.start()].strip(" ,.!:—-")


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text)
async def locked(message: Message):
    if access.entry(message.chat.id)["all"] or not _ours(message):
        return
    now = time.monotonic()
    if now - _said.get(message.chat.id, 0) < COOLDOWN:
        return
    _said[message.chat.id] = now
    await message.reply(NOTICE)
