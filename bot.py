import asyncio
from collections import defaultdict, deque

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

from ai.gemini import ask_gemini


TOKEN = __import__("os").getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")


bot = Bot(token=TOKEN)
dp = Dispatcher()


# Последние сообщения каждого чата
chat_history = defaultdict(
    lambda: deque(maxlen=8)
)


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

    # Только текстовые сообщения
    if not message.text:
        return

    # Не отвечаем ботам
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

    # Обращение к Маруське
    mentioned = (
        "маруська" in text_lower
        or "@botmaruska_bot" in text_lower
    )

    # Ответ на сообщение Маруськи
    replied_to_bot = (
        message.reply_to_message is not None
        and message.reply_to_message.from_user is not None
        and message.reply_to_message.from_user.id == bot.id
    )

    # Если к Маруське не обращались — молчим
    if not mentioned and not replied_to_bot:
        return

    # Контекст
    context = "\n".join(
        chat_history[chat_id]
    )

    prompt = f"""
Последние сообщения в группе:

{context}

Текущее сообщение:
{username}: {message.text}

Ответь именно на текущее сообщение.

Учитывай контекст разговора.

Если вопрос требует актуальной информации,
можешь использовать Google Search.

Не обрывай ответ.
Закончи предложение и мысль полностью.
"""

    try:

        answer, sources = await ask_gemini(
            prompt,
            use_search=True,
        )

        if not answer:
            await message.answer(
                "Я почему-то не смогла сформулировать ответ 🤔"
            )
            return

        # Добавляем источники, если Google Search действительно использовался
        if sources:

            unique_sources = []
            seen_urls = set()

            for source in sources:

                url = source["url"]

                if url in seen_urls:
                    continue

                seen_urls.add(url)
                unique_sources.append(source)

                if len(unique_sources) >= 3:
                    break

            if unique_sources:

                source_text = "\n\n🔎 Источники:\n"

                for source in unique_sources:

                    source_text += (
                        f'• <a href="{source["url"]}">'
                        f'{source["title"]}</a>\n'
                    )

                answer += source_text

        await message.answer(
            answer,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )

    except Exception as e:

        print(
            "========== GEMINI ERROR =========="
        )
        print(
            type(e).__name__,
            str(e)
        )
        print(
            "=================================="
        )

        error_text = str(e).lower()

        if (
            "quota" in error_text
            or "429" in error_text
            or "resource_exhausted" in error_text
        ):

            await message.answer(
                "Я сегодня уже устала 😴\n"
                "Бесплатный лимит Gemini закончился. "
                "Попробуйте завтра."
            )

        else:

            await message.answer(
                "Что-то я сейчас задумалась 🤔"
            )


async def main():

    print(
        "==================================="
    )
    print(
        "МАРУСЬКА ЗАПУЩЕНА!"
    )
    print(
        "Gemini подключён"
    )
    print(
        "Google Search подключён"
    )
    print(
        "==================================="
    )

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
