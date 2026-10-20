"""
Базовые команды: /start, /гайд (он же /help), /ping.
И ответ на «Мара, что ты умеешь» — рассказ о возможностях для обычного человека.
"""

import asyncio
import logging
import re
from html import escape

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardMarkup, Message

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
    "♟ <b>Игры в чате</b> — /игры: крестики-нолики, шашки, морской бой, камень-ножницы-бумага, орёл или решка\n"
    "/random чай, кофе — выбрать за тебя\n"
    "/8ball вопрос — шар предсказаний\n"
    "/stopgame — остановить раунд\n\n"

    "🔮 <b>Ещё</b>\n"
    "Мара, предскажи — предсказание\n"
    "Мара, покажи меня (или «покажи Юлю») — портрет: котик или обезьянка\n"
    "Мара, мяу — просто котик\n"
    "Мара, погода и город — прогноз (например: Мара, погода Казань)\n\n"

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
    "🎯 «Мара, кто сегодня улитка?», «Мара, кто меня сегодня любит?» — случайный участник\n"
    "🔮 «Мара, кто я?», «Мара, кто @ник?» или ответом «Мара, кто это?» — характеристика по памяти\n"
    "📊 «Мара, инфа что …» — вероятность в процентах\n"
    "🎂 «мой др 15.03» или /др — день рождения; «дни рождения» — ближайшие в группе\n\n"

    "🃏 <b>Арена</b> — /arena или /game: Дурак онлайн, турниры и призы\n"
    "🏆 <b>Мини-турнир</b> — когда админ откроет запись, жми «Записаться»: 6 мест, один стол на вылет\n\n"

    "⚙️ <b>Ещё</b>\n"
    "/features — что включено в группе\n"
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
    "• Мара, покажи меня или «Мара, покажи Юлю» — портрет: котик или обезьянка\n"
    "• Мара, мяу — просто котик\n"
    "• Мара, погода и город — прогноз в любом городе (Мара, погода Казань)\n"
    "• /радио — русские и украинские станции\n"
    "• /8ball вопрос — шар предсказаний, /random чай, кофе — выбрать за тебя\n\n"

    "🃏 <b>Арена</b> — наш Дурак онлайн: подкидной и переводной, от 2 до 6 человек, "
    "турниры и призы. Кнопка внизу, /arena или просто «арена».\n\n"

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
    "• «Мара, кто сегодня улитка?» — выберу кого-нибудь из чата\n"
    "• «Мара, кто я?» — расскажу, какой ты в чате, по моей памяти\n"
    "• «Мара, инфа что …» — скажу, насколько это правда, в процентах\n"
    "• «гармония» ответом на сообщение — совместимость в процентах\n"
    "• /marry в ответ на сообщение — предложить брак, /marriages — все пары\n"
    "• «мой др 15.03» — запомню день рождения, «дни рождения» — ближайшие\n"
    "• /срок — сколько ты в группе (ответом — про другого)\n"
    "• + или − ответом на сообщение — рейтинг\n\n"

    "📊 <b>Статистика группы</b>\n"
    "• «топ болтунов» — кто больше всех написал\n"
    "• «топ слов за неделю», «топ сообщений за месяц»\n"
    "• /digest — итоги недели, /profile — твой профиль\n\n"

    "Все команды — /гайд."
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
    from features.arena_promo import games_buttons

    try:
        buttons = await games_buttons(message.bot, message.chat.id, message.chat.type in ("group", "supergroup"))
    except Exception:
        # Кнопки — приятное дополнение: без них рассказ всё равно уйдёт
        logger.warning("ABILITIES: не удалось собрать кнопки", exc_info=True)
        buttons = []

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
        "Добавь меня в группу и напиши там <code>/гайд</code> — "
        "покажу, что умею."
    )


@router.message(Command("гайд", "help", ignore_case=True))
async def help_handler(message: Message):
    await message.answer(HELP_TEXT)


ADMIN_HELP_TEXT = (
    "🛡 <b>Команды для админов</b>\n\n"

    "<b>Модерация</b> — ответом на сообщение нарушителя:\n"
    "/warn причина — предупреждение\n"
    "/mute 30 — мут на 30 минут, /unmute — снять\n"
    "/tban 1д — бан на время (ч, д)\n"
    "/ban — бан навсегда, /unban — разбан\n"
    "/kick — выкинуть (вернуться можно)\n"
    "/delete — удалить сообщение (и Мары тоже)\n\n"

    "<b>Чат</b>\n"
    "/lock — закрыть чат (пишут только админы), /unlock — открыть\n"
    "/welcomevideo — ответом на видео: приветствие новичков с видео\n\n"

    "<b>Мини-турнир</b>\n"
    "/старт турнир 5000 — запись на турнир (6 мест, приз — кредиты в «Дурак Онлайн»)\n"
    "/стоп турнир — отменить запись или турнир\n\n"

    "<b>Настройки</b>\n"
    "/settings — админка: что включить в группе\n"
    "Автомодерация (антифлуд, ссылки, стоп-слова, антимат) — /settings → Модерация\n\n"

    "Команды для всех — /гайд"
)

# Ответ в группе про личку — убираем через минуту, чтобы не висел
NOTICE_TTL = 60


async def _delete_later(message: Message, delay: int) -> None:
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except Exception:
        pass


@router.message(Command("helpadmin", "adminhelp"))
async def admin_help_handler(message: Message):
    """Команды модерации видят только админы: в группе Мара шлёт их в личку."""
    from settings.handler import GROUP_CHATS, is_admin, is_owner

    user = message.from_user
    if user is None or user.is_bot:
        return

    if message.chat.type not in GROUP_CHATS:
        # В личке — только главным админам: админ группы зовёт /helpadmin в своей группе
        if is_owner(user.id):
            await message.answer(ADMIN_HELP_TEXT)
        else:
            await message.answer("🛡 Напиши /helpadmin в группе, где ты админ, — пришлю список сюда.")
        return

    # Саму команду из чата убираем: остальным незачем видеть, что её звали
    try:
        await message.delete()
    except Exception:
        pass

    if not await is_admin(message, message.bot):
        return

    try:
        await message.bot.send_message(user.id, ADMIN_HELP_TEXT)
        text = f"📬 {escape(display_name_of(user))}, отправила команды для админов тебе в личку."
    except Exception:
        text = (f"📬 {escape(display_name_of(user))}, не могу написать тебе в личку: "
                "открой меня, нажми «Старт» и повтори /helpadmin.")

    notice = await message.answer(text)
    asyncio.create_task(_delete_later(notice, NOTICE_TTL))


@router.message(Command("ping"))
async def ping_handler(message: Message):
    await message.answer("🏓 Мара на связи.")
