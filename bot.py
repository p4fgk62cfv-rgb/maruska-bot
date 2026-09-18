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

gemini_client = genai.Client(
    api_key=GEMINI_API_KEY
)


# Последние сообщения каждого чата
chat_history = defaultdict(
    lambda: deque(maxlen=6)
)


SYSTEM_PROMPT = """
Ты — Маруська, живая девушка и участница Telegram-группы.

У тебя женский характер и живая манера общения.
Общайся естественно, как обычная девушка в компании.

Отвечай на русском языке, если пользователь пишет по-русски.

Будь дружелюбной, немного дерзкой, с чувством юмора.
Можешь шутить, подкалывать и использовать эмодзи,
если это подходит ситуации.

Не отвечай слишком длинно без необходимости.

Всегда заканчивай мысль и не обрывай предложения.

Не выдумывай факты.

Не говори, что ты языковая модель или ИИ,
если пользователь прямо не спрашивает об этом.

Если тебя спрашивают, кто ты, отвечай естественно:
ты — Маруська, девушка-участница этой компании.

Главная задача — поддерживать живой разговор
и быть полезной участницей группы.
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
        "Чтобы поговорить со мной, напиши "
        "«Маруська» или ответь на моё сообщение."
    )


@dp.message(Command("ping"))
async def ping(message: Message):
    await message.answer(
        "Маруська на связи 🟢"
    )


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

    # Сохраняем сообщение
    chat_history[chat_id].append(
        f"{username}: {message.text}"
    )

    text_lower = message.text.lower()

    # Проверяем обращение к Маруське
    mentioned = (
        "маруська" in text_lower
        or "@botmaruska_bot" in text_lower
    )

    # Проверяем ответ на сообщение Маруськи
    replied_to_bot = (
        message.reply_to_message is not None
        and message.reply_to_message.from_user is not None
        and message.reply_to_message.from_user.id == bot.id
    )

    # Если к Маруське не обращались — ничего не делаем
    if not mentioned and not replied_to_bot:
        return

    # Формируем контекст
    context = "\n".join(
        chat_history[chat_id]
    )

    prompt = f"""
Контекст последних сообщений:

{context}

Текущее сообщение:
{username}: {message.text}

Ответь именно на текущее сообщение.
Не обрывай ответ.
Закончи предложение и мысль полностью.
"""


    try:

        response = await gemini_client.aio.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
            config={
                "system_instruction": SYSTEM_PROMPT,
                "temperature": 0.7,
                "max_output_tokens": 1000,
            },
        )

        # Диагностика Gemini
        print("========== GEMINI DEBUG ==========")
        print("GEMINI RESPONSE:", response)
        print("GEMINI TEXT:", repr(response.text))

        try:
            if response.candidates:
                print(
                    "FINISH REASON:",
                    response.candidates[0].finish_reason
                )
        except Exception as debug_error:
            print(
                "FINISH REASON ERROR:",
                debug_error
            )

        print("===================================")

        answer = (
            response.text or ""
        ).strip()

        if answer:
            await message.answer(answer)
        else:
            await message.answer(
                "Я почему-то не смогла сформулировать ответ 🤔"
            )


    except Exception as e:

        print("========== GEMINI ERROR ==========")
        print(type(e).__name__, str(e))
        print("==================================")

        await message.answer(
            "Что-то я сейчас задумалась 🤔"
        )


async def main():

    print("===================================")
    print("МАРУСЬКА ЗАПУЩЕНА!")
    print("Gemini подключён")
    print("===================================")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
