import asyncio
import os
from collections import defaultdict, deque

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

from ai.gemini import ask_gemini
from database.database import init_db


# =========================
# НАСТРОЙКИ
# =========================

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")


# =========================
# TELEGRAM
# =========================

bot = Bot(token=TOKEN)
dp = Dispatcher()


# =========================
# ВРЕМЕННАЯ ПАМЯТЬ ЧАТА
# =========================

chat_history = defaultdict(
    lambda: deque(maxlen=8)
)


# =========================
# /START
# =========================

@dp.message(CommandStart())
async def start(message: Message):

    await message.answer(
        "Привет! Я Маруська 💜\n"
        "Я уже подключила свой мозг, поиск и память 😉"
    )


# =========================
# /HELP
# =========================

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


# =========================
# /PING
# =========================

@dp.message(Command("ping"))
async def ping(message: Message):

    await message.answer(
        "Маруська на связи 🟢"
    )


# =========================
# AI
# =========================

@dp.message()
async def ai_message(message: Message):

    # Только текст
    if not message.text:
        return

    # Игнорируем других ботов
    if message.from_user and message.from_user.is_bot:
        return

    chat_id = message.chat.id

    username = (
        message.from_user.first_name
        if message.from_user
        else "Пользователь"
    )

    # =========================
    # СОХРАНЯЕМ ВРЕМЕННЫЙ КОНТЕКСТ
    # =========================

    chat_history[chat_id].append(
        f"{username}: {message.text}"
    )

    text_lower = message.text.lower()

    # =========================
    # ОБРАЩЕНИЕ К МАРУСЬКЕ
    # =========================

    mentioned = (
        "маруська" in text_lower
        or "@botmaruska_bot" in text_lower
    )

    # =========================
    # ОТВЕТ НА СООБЩЕНИЕ БОТА
    # =========================

    replied_to_bot = (
        message.reply_to_message is not None
        and message.reply_to_message.from_user is not None
        and message.reply_to_message.from_user.id == bot.id
    )

    # Если к Маруське не обращались — молчим
    if not mentioned and not replied_to_bot:
        return

    # =========================
    # КОНТЕКСТ
    # =========================

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
используй Google Search.

Если актуальная информация не требуется,
не используй поиск.

Не выдумывай факты.

Не говори о себе как о безличном ассистенте.
Ты — Маруська, участница этой компании.

Отвечай естественно.

Не обрывай ответ.
Закончи предложение и мысль полностью.
"""

    # =========================
    # GEMINI
    # =========================

    try:

        answer, sources = await ask_gemini(
            prompt,
            use_search=True,
        )

        answer = (
            answer or ""
        ).strip()

        # =========================
        # ПУСТОЙ ОТВЕТ
        # =========================

        if not answer:

            await message.answer(
                "Я почему-то не смогла сформулировать ответ 🤔"
            )

            return

        # =========================
        # ИСТОЧНИКИ GOOGLE SEARCH
        # =========================

        if sources:

            unique_sources = []
            seen_urls = set()

            for source in sources:

                url = source.get("url")

                if not url:
                    continue

                if url in seen_urls:
                    continue

                seen_urls.add(url)

                unique_sources.append(
                    source
                )

                if len(unique_sources) >= 3:
                    break

            if unique_sources:

                source_text = (
                    "\n\n🔎 <b>Источники:</b>\n"
                )

                for source in unique_sources:

                    title = (
                        source.get("title")
                        or "Источник"
                    )

                    url = source["url"]

                    source_text += (
                        f'• <a href="{url}">'
                        f'{title}</a>\n'
                    )

                answer += source_text

        # =========================
        # ОТВЕТ
        # =========================

        await message.answer(
            answer,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )

    # =========================
    # ОШИБКИ
    # =========================

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

        # Лимит Gemini
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


# =========================
# ЗАПУСК
# =========================

async def main():

    print(
        "==================================="
    )

    print(
        "Подключение к PostgreSQL..."
    )

    # Создаём таблицы при запуске
    await init_db()

    print(
        "PostgreSQL подключён"
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


# =========================
# ENTRY POINT
# =========================

if __name__ == "__main__":

    asyncio.run(main())
