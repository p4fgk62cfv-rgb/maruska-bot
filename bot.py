import os
import asyncio
from collections import defaultdict, deque

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from google import genai


TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is not set")


bot = Bot(token=TOKEN)
dp = Dispatcher()

gemini_client = genai.Client(api_key=GEMINI_API_KEY)


# Небольшой контекст чата
chat_history = defaultdict(lambda: deque(maxlen=6))


SYSTEM_PROMPT = """
Ты — Маруська, живая участница Telegram-группы.

Отвечай естественно, коротко и по делу.
Русский язык используй по умолчанию.
Не выдумывай факты.
Можно использовать юмор, иронию и эмодзи.
Не упоминай, что ты ИИ, если тебя прямо об этом не спрашивают.
"""


@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "Привет! Я Маруська 💜"
    )


@dp.message(Command("help"))
async def help_command(message: Message):
    await message.answer(
        "Команды:\n"
        "/start — запуск\n"
        "/help — помощь\n"
        "/ping — проверка связи\n\n"
        "Напиши «Маруська» или ответь на моё сообщение."
    )


@dp.message(Command("ping"))
async def ping(message: Message):
    await message.answer("Маруська на связи 🟢")


@dp.message()
async def ai_message(message: Message):

    if not message.text:
        return

    if message.from_user and message.from_user.is_bot:
        return

    chat_id = message.chat.id

    username = (
        message.from_user.first_name
        if message.from_user
        else "Пользователь"
    )

    # Сохраняем сообщение
    chat_history[chat_id].append(
        f"{username}: {message.text}"
    )

    text_lower = message.text.lower()

    mentioned = (
        "маруська" in text_lower
        or "@botmaruska_bot" in text_lower
    )

    replied_to_bot = (
        message.reply_to_message is not None
        and message.reply_to_message.from_user is not None
        and message.reply_to_message.from_user.id == bot.id
    )

    if not mentioned and not replied_to_bot:
        return

    context = "\n".join(chat_history[chat_id])

    prompt = f"""
Контекст:
{context}

Сообщение:
{username}: {message.text}

Ответь пользователю.
"""

    try:

        response = await gemini_client.aio.models.generate_content(
    model="gemini-3.6-flash",
    contents=prompt,
    config={
        "system_instruction": SYSTEM_PROMPT,
        "temperature": 0.7,
        "max_output_tokens": 500,
    },
)

print("GEMINI RESPONSE:", response)
print("GEMINI TEXT:", repr(response.text))

answer = (response.text or "").strip()

        if answer:
            await message.answer(answer)

    except Exception as e:

        print(f"Gemini error: {e}")

        await message.answer(
            "Что-то я задумалась 🤔"
        )


async def main():

    print("Маруська запущена!")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

