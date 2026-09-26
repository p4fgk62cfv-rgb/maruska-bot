"""
Рыбалка в чате: открыть игру и посмотреть топ рыбаков.

  /fishing, /fish, «рыбалка» — кнопка игры. В группе ссылка несёт
      id группы (startapp=g<id>): тогда крупный улов объявляется в чате,
      а топ считается среди участников группы.
  /fishtop, «топ рыбаков» — лучшие рыбаки группы.

Имя бота берётся у Telegram, а не зашивается в код: ссылка не
сломается, если бота переименуют.

Для ссылки в группе в BotFather должно быть мини-приложение с коротким
именем «fishing» (/newapp → адрес https://<домен>/fishing).
"""

import re
from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from settings.store import is_enabled


router = Router(name="fishing")

OPEN_WORDS = {"рыбалка", "рыбачим", "на рыбалку", "🎣 рыбалка", "го на рыбалку"}
TOP_RE = re.compile(r"^\s*/?\s*топ\s+рыбак(ов|и)?\s*[!?.]*\s*$", re.IGNORECASE)


def start_param(chat_id: int) -> str:
    """-1001234567890 → «g1001234567890» (Telegram пускает только буквы, цифры, _ и -)."""
    return f"g{abs(chat_id)}"


def format_top(people: list[dict]) -> str:
    if not people:
        return "🎣 В группе ещё никто не рыбачил. /fishing — открыть игру"

    medals = ("🥇", "🥈", "🥉")
    lines = ["🎣 <b>Лучшие рыбаки группы</b>\n"]

    for place, p in enumerate(people, start=1):
        mark = medals[place - 1] if place <= 3 else f"{place}."
        lines.append(f"{mark} <b>{escape(p['name'])}</b> — рекорд {p['best']} кг · улов {p['catches']}")

    return "\n".join(lines)


async def open_fishing(message: Message):
    from fishing import service as fs
    from webapp.server import public_url

    if not fs.settings()["enabled"]:
        await message.reply("🎣 Рыбалка сейчас на перерыве.")
        return

    group = message.chat.type in ("group", "supergroup")

    if group and not is_enabled(message.chat.id, "fishing"):
        await message.reply("🎣 Рыбалка в этой группе выключена (/settings).")
        return

    base = public_url()

    if not base:
        await message.reply("🎣 Рыбалка пока недоступна: у бота не настроен публичный адрес.")
        return

    if group:
        # В группах Telegram не даёт кнопки web_app — только ссылку на мини-приложение
        me = await message.bot.me()
        button = InlineKeyboardButton(
            text="🎣 Открыть рыбалку",
            url=f"https://t.me/{me.username}/fishing?startapp={start_param(message.chat.id)}",
        )
    else:
        button = InlineKeyboardButton(text="🎣 Открыть рыбалку", web_app=WebAppInfo(url=f"{base}/fishing"))

    await message.answer(
        "🎣 <b>Рыбалка Маруськи</b>\n\n"
        "Выбирай водоём, забрасывай, вываживай и собирай коллекцию. "
        "Алмазы и опыт — общие с Марой.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[button]]),
    )


@router.message(Command("fishing", "fish"))
async def fishing_command(message: Message):
    await open_fishing(message)


def is_open_request(message: Message) -> bool:
    """
    «рыбалка» отдельным сообщением — открыть игру. В ответ на чужое
    сообщение это встроенное действие «позвал(а) на рыбалку» с картинкой,
    его не перехватываем.
    """
    return message.reply_to_message is None and (message.text or "").strip().lower() in OPEN_WORDS


@router.message(is_open_request)
async def fishing_text(message: Message):
    await open_fishing(message)


async def show_top(message: Message):
    if message.chat.type not in ("group", "supergroup"):
        await message.reply("🎣 Топ рыбаков считается в группе.")
        return

    if not is_enabled(message.chat.id, "fishing"):
        await message.reply("🎣 Рыбалка в этой группе выключена (/settings).")
        return

    from fishing import service as fs

    await message.answer(format_top(await fs.leaderboard(message.chat.id, 10)))


@router.message(Command("fishtop"))
async def fishtop_command(message: Message):
    await show_top(message)


@router.message(F.text.func(lambda t: TOP_RE.match(t or "") is not None))
async def fishtop_text(message: Message):
    await show_top(message)
