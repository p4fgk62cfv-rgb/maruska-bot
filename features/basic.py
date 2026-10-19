"""
Базовые команды: /start, /help, /ping.
И ответ на «Мара, что ты умеешь» — рассказ о возможностях для обычного человека.
"""

import logging
import re

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from botcontext import display_name_of, is_addressed

from database.repository import create_profile_if_needed, save_user


logger = logging.getLogger("maruska.basic")

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
    "Мара, нарисуй кота в шляпе — картинка от Мары (или /нарисуй …)\n"
    "♟ <b>Игры в чате</b> — /игры: крестики-нолики, шашки, морской бой, камень-ножницы-бумага, орёл или решка\n"
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

    "🎣 <b>Рыбалка</b> — /fishing открыть игру, /fishtop лучшие рыбаки группы\n"
    "📻 <b>Радио</b> — /радио или /radio: русские и украинские станции\n"
    "💞 <b>Пара дня</b> — «пара дня» или /pair\n"
    "💍 <b>Браки</b> — /marry в ответ на сообщение, /marriage, /marriages, /divorce\n\n"

    "🗣 <b>Топ болтунов</b> — «топ болтунов» или /chatters: кто больше всех написал сегодня\n"
    "📊 «топ сообщений за неделю», «топ слов за месяц» (день / неделю / месяц) "
    "или /topmessages и /topwords с периодом\n"
    "📅 /срок — сколько ты в группе; ответом или /срок @ник — про другого\n"
    "💞 «гармония» ответом на сообщение или «гармония @ник» — совместимость в процентах\n"
    "🎂 «мой др 15.03» или /др — день рождения; «дни рождения» — ближайшие в группе\n\n"

    "🛡 <b>Автомодерация</b> — включается в /settings → Модерация:\n"
    "антифлуд, ссылки, стоп-слова, предупреждения\n\n"

    "🛡 <b>Модерация</b> (для админов, реплаем)\n"
    "/warn причина — предупредить\n"
    "/mute 30 — замутить, /unmute — размутить\n"
    "/tban 1д — бан на время\n"
    "/ban, /unban, /kick — бан, разбан, выкинуть\n"
    "/delete — удалить сообщение (и Мары тоже)\n"
    "/lock, /unlock — закрыть и открыть чат\n\n"

    "⚙️ <b>Настройки</b>\n"
    "/settings — что включить (для админов)\n"
    "/features — что сейчас включено\n"
    "/myid — узнать свой ID"
)


ABILITIES_TEXT = (
    "👋 Я Мара — болтаю с группой, устраиваю игры и раздаю алмазы. Вот что я умею.\n\n"

    "💬 <b>Поговорить</b>\n"
    "Позови по имени: <b>Мара, как дела?</b> — или ответь на моё сообщение. "
    "Отвечу на вопрос, подскажу, пошучу.\n\n"

    "🍺 <b>Угощать и дарить</b>\n"
    "Ответь человеку одним-двумя словами: <i>пиво, кофе, пицца, торт, розы, котика, обнять, "
    "поцеловать, баня</i> — и я красиво это обыграю. Больше 200 вариантов.\n\n"

    "🔮 <b>Развлечения</b>\n"
    "• Мара, предскажи — предсказание\n"
    "• Мара, нарисуй кота в шляпе — картинка\n"
    "• Мара, покажи меня — твой портрет в виде котика\n"
    "• Мара, мяу — просто котик\n"
    "• Мара, погода в Праге — прогноз\n"
    "• /радио — русские и украинские станции\n"
    "• /8ball вопрос — шар предсказаний, /random чай, кофе — выбрать за тебя\n\n"

    "🃏 <b>Арена</b> — наш Дурак онлайн: подкидной и переводной, от 2 до 6 человек, "
    "турниры и призы. Кнопка внизу или /game.\n\n"

    "🎮 <b>Игры</b>\n"
    "• «крокодил» — рисуй и отгадывай слово\n"
    "• /игры — крестики-нолики, шашки, морской бой, камень-ножницы-бумага, орёл или решка\n"
    "• /dice 2d6 — кубики, /coin — монетка\n"
    "• 🎣 /fishing — рыбалка (кнопка внизу), /fishtop — лучшие рыбаки\n\n"

    "💎 <b>Алмазы и прогресс</b>\n"
    "• /bonus — ежедневный бонус, /balance — сколько у тебя\n"
    "• /shop — магазин, /gift — подарить алмазы\n"
    "• /level — уровень и опыт, /achievements — достижения\n"
    "• /rich и /toplevel — самые богатые и самые опытные\n\n"

    "💞 <b>Про людей в группе</b>\n"
    "• «пара дня» — случайная пара, можно спрашивать сколько угодно\n"
    "• «гармония» ответом на сообщение — совместимость в процентах\n"
    "• /marry в ответ на сообщение — предложить брак, /marriages — все пары\n"
    "• «мой др 15.03» — запомню день рождения, «дни рождения» — ближайшие\n"
    "• /срок — сколько ты в группе (ответом — про другого)\n"
    "• + или − ответом на сообщение — рейтинг\n\n"

    "📊 <b>Статистика группы</b>\n"
    "• «топ болтунов» — кто больше всех написал\n"
    "• «топ слов за неделю», «топ сообщений за месяц»\n"
    "• /digest — итоги недели, /profile — твой профиль\n\n"

    "Все команды — /help."
)

_ABILITIES_RE = re.compile(
    r"что\s+(?:ты\s+|вы\s+)?(?:умеешь|можешь|умеете|можете)"
    r"|что\s+ты\s+за\s+бот|чем\s+(?:ты\s+)?(?:занимаешься|полезна)"
    r"|(?:твои|свои|все)\s+(?:команды|функции|возможности)"
    r"|(?:команды|функции|возможности)\s+(?:бота|мары|марусь)"
    r"|какие\s+у\s+тебя\s+(?:команды|функции|возможности)"
    r"|^\W*(?:мар\w+|марус\w+)[\s,]+(?:помощь|помоги|хелп|help)\W*$",
    re.IGNORECASE,
)


def asks_abilities(message: Message) -> bool:
    """«Мара, что ты умеешь» и похожее — к Маре обратились и спросили про возможности."""
    if not message.text or message.text.startswith("/"):
        return False
    if message.from_user is None or message.from_user.is_bot:
        return False
    return bool(_ABILITIES_RE.search(message.text)) and is_addressed(message)


async def _abilities_keyboard(message: Message) -> InlineKeyboardMarkup | None:
    """Кнопки «Арена» и «Рыбалка» — те, что сейчас доступны в этом чате."""
    group = message.chat.type in ("group", "supergroup")
    buttons = []
    try:
        me = await message.bot.me()
        username = me.username or ""

        from games.arena import play_button

        arena = play_button(username, group)
        if arena is not None:
            buttons.append(arena.model_copy(update={"text": "🃏 Арена — дурак онлайн"}))

        from fishing import service as fs
        from games.fishing import fishing_button
        from settings.store import is_enabled
        from webapp.server import public_url

        base = public_url()
        if base and fs.settings()["enabled"] and not (group and not is_enabled(message.chat.id, "fishing")):
            fishing = fishing_button(username, message.chat.id, group, base, text="🎣 Рыбалка")
            buttons.append(fishing)
    except Exception:
        # Кнопки — приятное дополнение: без них рассказ всё равно уйдёт
        logger.warning("ABILITIES: не удалось собрать кнопки", exc_info=True)

    return InlineKeyboardMarkup(inline_keyboard=[[b] for b in buttons]) if buttons else None


# Отвечаем сами, без нейросети: так ответ точный и приходит всегда —
# и в тихом режиме, и когда у нейросетей кончился лимит
@router.message(asks_abilities)
async def abilities_handler(message: Message):
    await message.reply(ABILITIES_TEXT, reply_markup=await _abilities_keyboard(message))


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
