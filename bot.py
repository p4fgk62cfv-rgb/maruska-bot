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


# Последние сообщения по каждому чату
chat_history = defaultdict(lambda: deque(maxlen=12))


SYSTEM_PROMPT = """
Ты — Маруська, дружелюбная и живая участница Telegram-группы.

Общайся естественно, как обычный человек в чате.

Отвечай на русском языке, если пользователь не использует другой язык.

Не говори, что ты языковая модель или искусственный интеллект,
если это не требуется вопросом.

Не выдумывай факты.

Не отвечай слишком длинно без необходимости.

Можешь использовать юмор, иронию и эмодзи, но не перебарщивай.

Твоя задача — поддерживать разговор и быть полезной участницей группы.
"""


@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "Привет! Я Маруська 💜\n"
        "Теперь я умею разговаривать с вами 😏"
    )


@dp.message(Command("help"))
async def help_command(message: Message):
    await message.answer(
        "Команды Маруськи:\n"
        "/start — запустить бота\n"
        "/help — помощь\n"
        "/ping — проверить связь\n\n"
        "Чтобы поговорить со мной — просто напиши "
        "«Маруська» или упомяни @BotMaruska_bot."
    )


@dp.message(Command("ping"))
async def ping(message: Message):
    await message.answer("Маруська на связи 🟢")


@dp.message()
async def ai_message(message: Message):

    # Игнорируем сообщения без текста
    if not message.text:
        return

    # Игнорируем сообщения от ботов
    if message.from_user and message.from_user.is_bot:
        return

    chat_id = message.chat.id

    username = (
        message.from_user.first_name
        if message.from_user
        else "Пользователь"
    )

    # Сохраняем сообщение в историю
    chat_history[chat_id].append(
        f"{username}: {message.text}"
    )

    # Проверяем обращение к Маруське
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

    # Контекст последних сообщений
    context = "\n".join(chat_history[chat_id])

    prompt = f"""
Последние сообщения в группе:

{context}

Текущее сообщение пользователя:
{username}: {message.text}

Ответь на текущее сообщение.
"""

    try:

        response = await gemini_client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config={
                "system_instruction": SYSTEM_PROMPT,
                "temperature": 0.8,
                "max_output_tokens": 500,
            },
        )

        answer = response.text.strip()

        if answer:
            await message.answer(answer)

    except Exception as e:

        print(f"Gemini error: {e}")

        await message.answer(
            "Что-то я сейчас задумалась 🤔 Попробуй ещё раз."
        )


async def main():

    print("Маруська запущена!")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

