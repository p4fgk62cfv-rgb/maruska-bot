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
# ОПРЕДЕЛЕНИЕ, НУЖЕН ЛИ ПОИСК
# =========================

def needs_search(text: str) -> bool:

    text_lower = text.lower()

    search_triggers = [
        # актуальность
        "сегодня",
        "сейчас",
        "последние новости",
        "последние события",
        "что нового",
        "актуально",

        # поиск
        "найди",
        "поищи",
        "поиск",
        "гугл",
        "google",

        # цены
        "цена",
        "цены",
        "сколько стоит",
        "стоимость",

        # курсы
        "курс",
        "курс евро",
        "курс доллара",
        "доллар",
        "евро",

        # погода
        "погода",
        "температура",
        "будет дождь",
        "будет снег",

        # сайты / сервисы
        "сайт",
        "официальный сайт",
        "ссылка",
        "где купить",
        "где найти",

        # расписания
        "расписание",
        "рейс",
        "вылет",
        "прилет",

        # обновления
        "новая версия",
        "последняя версия",
        "обновление",

        # новости
        "новости",
        "что произошло",
        "что случилось",
    ]

    return any(
        trigger in text_lower
        for trigger in search_triggers
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
    # СОХРАНЯЕМ КОНТЕКСТ
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

    # =========================
    # НУЖЕН ЛИ GOOGLE SEARCH
    # =========================

    use_search = needs_search(
        message.text
    )

    prompt = f"""
Последние сообщения в группе:

{context}

Текущее сообщение:
{username}: {message.text}

Ответь именно на текущее сообщение.

Учитывай контекст разговора.

Google Search уже выбран программой:
{use_search}

Если Google Search включён — используй его
для проверки актуальной информации.

Если Google Search выключен — отвечай
без поиска.

Не выдумывай факты.

Не говори о себе как о безличном ассистенте.
Ты — Маруська, участница этой компании.

Отвечай естественно.

Не обрывай ответ.
Закончи предложение и мысль полностью.
"""

    try:

        answer, sources = await ask_gemini(
            prompt,
            use_search=use_search,
        )

        answer = (
            answer or ""
        ).strip()

        if not answer:

            await message.answer(
                "Я почему-то не смогла сформулировать ответ 🤔"
            )

            return

        # =========================
        # ИСТОЧНИКИ
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
                "Сейчас Gemini не принимает запросы 😴\n"
                "Попробуй немного позже."
            )

        else:

            await message.answer(
                "Что-то я сейчас задумалась 🤔"
            )


# =========================
# MAIN
# =========================

async def main():

    print(
        "==================================="
    )

    print(
        "Подключение к PostgreSQL..."
    )

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


if __name__ == "__main__":

    asyncio.run(main())
