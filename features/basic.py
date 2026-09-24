"""
Базовые команды: /start, /help, /ping.
"""

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from botcontext import display_name_of

from database.repository import create_profile_if_needed, save_user


router = Router(name="basic")


HELP_TEXT = (
    "🤖 <b>Мара</b>\n\n"
    "💬 Позови по имени: <b>Мара, ...</b>\n"
    "Или ответь на моё сообщение.\n\n"

    "🎲 <b>Действия</b>\n"
    "Ответь человеку и напиши одним-двумя словами:\n\n"
    "🍺 Пиво, водка, вино, самогон, мохито\n"
    "☕ Кофе, чай, какао, квас, смузи\n"
    "🍕 Пицца, шаурма, борщ, пельмени, суши\n"
    "🍰 Торт, мороженое, пряник, халва\n"
    "🌹 Розы, пионы, ромашки, кактус\n"
    "🎁 Подарок, мишку, миллион, корону\n"
    "🐱 Котика, щенка, хомяка, попугая\n"
    "🚑 Дурку, скорую, такси, пожарных\n"
    "🤗 Обнять, целую, на ручки, погладить\n"
    "🧖 Баня, рыбалка, спортзал, селфи\n\n"
    "Больше 200 вариантов, фразы каждый раз разные.\n\n"

    "💎 <b>Алмазы</b>\n"
    "/bonus — ежедневный бонус\n"
    "/balance — баланс, /history — операции\n"
    "/rich — топ богачей\n"
    "/shop — магазин, /gift — подарить\n"
    "/inventory — что накопилось\n\n"

    "🎚 <b>Прогресс</b>\n"
    "/level — уровень и опыт\n"
    "/achievements — достижения\n"
    "/toplevel — топ по уровню\n\n"

    "🎮 <b>Игры</b>\n"
    "«крокодил» — рисуй и отгадывай\n"
    "/dice 2d6 — кубики, /coin — монетка\n"
    "/random чай, кофе — выбрать за тебя\n"
    "/8ball вопрос — шар предсказаний\n"
    "/stopgame — остановить раунд\n\n"

    "🔮 <b>Ещё</b>\n"
    "Мара, предскажи — предсказание\n"
    "Мара, покажи меня — портрет из котика\n"
    "Мара, мяу — просто котик\n"
    "Мара, погода в Праге — прогноз\n\n"

    "⭐ <b>Сообщество</b>\n"
    "+ или − реплаем — рейтинг\n"
    "/profile — профиль, /top — топ\n"
    "/digest — итоги недели\n"
    "/mydays — сколько ты здесь\n\n"

    "🛡 <b>Автомодерация</b> — включается в /settings → Модерация:\n"
    "антифлуд, ссылки, стоп-слова, предупреждения\n\n"

    "🛡 <b>Модерация</b> (для админов, реплаем)\n"
    "/warn причина — предупредить\n"
    "/mute 30 — замутить, /unmute — размутить\n"
    "/tban 1д — бан на время\n"
    "/ban, /unban, /kick — бан, разбан, выкинуть\n"
    "/lock, /unlock — закрыть и открыть чат\n\n"

    "⚙️ <b>Настройки</b>\n"
    "/settings — что включить (для админов)\n"
    "/features — что сейчас включено\n"
    "/myid — узнать свой ID"
)


@router.message(CommandStart())
async def start_handler(message: Message):
    if message.from_user:
        await save_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )

        # Человек сам написал боту в личку — теперь ему можно
        # отправлять личные рассылки (первыми боты писать не могут)
        if message.chat.type == "private":
            try:
                from database.repository import mark_dm_ok

                await mark_dm_ok(message.from_user.id, True)
            except Exception:
                pass

        await create_profile_if_needed(
            telegram_id=message.from_user.id,
            display_name=display_name_of(message.from_user),
        )

    await message.answer(
        "👋 Привет! Я Мара.\n\n"
        "Живу в групповых чатах: болтаю, веду рейтинг, раздаю алмазы "
        "и устраиваю игры.\n\n"
        "Добавь меня в группу и напиши там <code>/help</code> — "
        "покажу, что умею."
    )


@router.message(Command("help"))
async def help_handler(message: Message):
    await message.answer(HELP_TEXT)


@router.message(Command("ping"))
async def ping_handler(message: Message):
    await message.answer("🏓 Мара на связи.")
