"""
Общий контекст бота.

Здесь живёт то, что нужно всем модулям сразу: кто мы такие
в Telegram, как понять, что обратились к нам, и как назвать
человека. Раньше это лежало в bot.py, из-за чего любой новый
модуль тянул за собой весь файл.
"""

import re

from aiogram.types import Message


# Имена, на которые бот откликается.
# Принимаются падежные формы: Мара, Мару, Маре, Марой.
TRIGGER_PATTERN = (
    r"мар(?:а|у|ы|е|ой|ою|ке|ку)"
    r"|марус(?:я|ю|е|и|ька|ьку|ьке)"
    r"|маня"
)

TRIGGER_RE = re.compile(
    r"\b(?:" + TRIGGER_PATTERN + r")\b",
    re.IGNORECASE,
)


# Заполняется один раз при старте
BOT_ID: int = 0
BOT_USERNAME: str = ""


def set_identity(bot_id: int, username: str) -> None:
    global BOT_ID, BOT_USERNAME

    BOT_ID = bot_id
    BOT_USERNAME = username or ""


def display_name_of(user) -> str:
    if user is None:
        return "Пользователь"

    return user.first_name or user.username or "Пользователь"


def is_addressed(message: Message) -> bool:
    """
    Обратились ли к боту: по имени, через @упоминание или
    ответом на его сообщение.

    Намеренно НЕ смотрит на настройку "ai": погода, котики и
    предсказания вызываются тем же обращением, но живут по своим
    флагам. Иначе выключение ответов Мары молча убивало бы и их.
    """
    text = message.text or ""

    if message.chat.type == "private":
        return True

    if TRIGGER_RE.search(text):
        return True

    if BOT_USERNAME and f"@{BOT_USERNAME.lower()}" in text.lower():
        return True

    reply = message.reply_to_message

    if reply and reply.from_user and reply.from_user.id == BOT_ID:
        return True

    return False


def get_rank_info(karma: int) -> str:
    if karma >= 500:
        return "Легенда"
    if karma >= 250:
        return "Звезда"
    if karma >= 100:
        return "Авторитет"
    if karma >= 50:
        return "Уважаемый"
    if karma >= 10:
        return "Активист"

    return "Участник"
