"""Антимат: что считается матом, а что нет.  python test_antimat.py"""

import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", os.getenv("TEST_DATABASE_URL") or "postgresql://unused@localhost/unused")

from features.antimat import DEFAULT_WORDS, find_swear, parse_words  # noqa: E402

failures, checks = [], 0


def expect(label, got, want):
    global checks
    checks += 1
    if got != want:
        failures.append(f"  {label}: получили {got!r}, ждали {want!r}")


words = parse_words(DEFAULT_WORDS)

SWEARS = [
    "ну ты и сука", "СУКА!!!", "иди нахуй", "хуйня какая-то", "похуй вообще", "пиздец",
    "распиздяй", "бля, опять", "блядь", "заебал уже", "ебать ты", "долбоеб", "уебок",
    "мудак", "пидорас", "ты гандон", "охуеть", "выебнулся",
    # маскировка
    "xуй", "cyka", "сууука", "х.у.й", "х у й", "п.и.з.д.е.ц","бляяяяя", "ХУЙ",
]
CLEAN = [
    "тебе привет", "свежий хлеб", "небо голубое", "он всё страхует", "политические дебаты",
    "оскорблять нельзя", "хулиган", "сучок на дереве", "ребята, привет", "употреблять",
    "колебания", "психуешь?", "у меня всё хорошо", "застрахуемся", "ухудшение", "хулить",
    "команда", "щебетать", "небольшой", "учебник", "", "123",
]

for text in SWEARS:
    expect(f"мат «{text}»", find_swear(text, words) is not None, True)
for text in CLEAN:
    expect(f"не мат «{text}»", find_swear(text, words), None)

# ---------- Умный словарь и маскировка ----------
from features.antimat import is_builtin_swear, mute_minutes  # noqa: E402

SMART = [
    # формы и приставки
    "хуйло", "нихуя", "охуенный", "пиздюк", "выблядок", "ебанутый", "заебись", "отъебись",
    "подъебка", "уебище", "долбоёб", "еблан", "сучка", "сукин", "мудозвон", "пидрила",
    "залупа", "мандавошка", "дрочить", "херня", "нахер", "похер", "херачить", "хули",
    # звёздочки и @ вместо букв
    "х*й", "х**", "п*зда", "пи*да", "бл*ть", "бл@ть", "еб#ть", "нах*й",
    # транслит
    "huy", "hui", "pizda", "blyat", "suka", "ebat", "nahuy", "hujnja",
    # «i» и цифры, стильные шрифты, невидимые символы, ударения
    "пiзда", "п1зда", "6ля", "3аебал", "ｈуй", "𝐱уй", "х\u200bуй", "х\u0301уй",
    # буквы через смайлики, слово с пробелом внутри
    "х🙂у🙂й", "ху йня", "бл ять опять", "ну ты п и з д а конечно",
]
SAFE = [
    "себе", "себестоимость", "вебинар", "Ебург", "всухую", "сухую траву", "глухую ночь",
    "сабля", "команда", "мандарин", "мандат", "мандраж", "херувим", "Херсон", "херес",
    "хулиган", "хурма", "хуже", "Хуан", "сучок", "сучья", "мудрый", "скипидар", "шлюз",
    "гондола", "суккулент", "Ебола", "оскорблять", "употребление", "корабля", "застрахуйся",
    "психуй", "колебаться", "погребение", "хлебать", "небось", "**жирный текст**",
    "her", "other", "hue", "ebay", "webapp", "debate", "hello", "в хлеб", "на небо", "я и ты",
    # команды бота, упоминания и ссылки — не слова человека
    "/job", "/job@BotMaruska_bot", "/jobs", "job", "@suka_bot привет", "https://example.com/huy",
    "/top", "/profile", "/eban", "oxygen", "heritage", "herald",
    # два обычных слова не складываются в мат на стыке
    "тип изделия", "суп издалека", "топ изданий", "поп издавна",
    # найдены перебором всех словоформ словаря
    "уподобляться", "обособлять", "пособлять", "подсобляя", "сподобляться", "подебелее",
    "подебильнее", "всеблагой", "всебурятский", "Себастьян", "Себастиановна",
]
for text in SMART:
    expect(f"умный словарь ловит «{text}»", find_swear(text, [], builtin=True) is not None, True)
for text in SAFE:
    expect(f"умный словарь не трогает «{text}»", find_swear(text, [], builtin=True), None)
expect("без умного словаря и списка — ничего", find_swear("хер", []), None)
expect("мат после команды ловится", find_swear("/job сука", [], builtin=True) is not None, True)
expect("исключение админа", find_swear("херня", [], builtin=True, allow=parse_words("херн*")), None)
expect("исключение не мешает другому мату", find_swear("херня, сука", [], builtin=True, allow=parse_words("херн*")) is not None, True)
expect("корень с приставкой", is_builtin_swear("распиздяй"), True)

# Мут удваивается: 30 → 60 → 120 мин, но не больше 7 дней
expect("первый мут", mute_minutes(30, 0, True), 30)
expect("второй мут вдвое", mute_minutes(30, 1, True), 60)
expect("третий мут", mute_minutes(30, 2, True), 120)
expect("потолок 7 дней", mute_minutes(1440, 5, True), 7 * 1440)
expect("без удвоения", mute_minutes(30, 3, False), 30)
expect("без мута", mute_minutes(0, 3, True), 0)

# Свой список: слово целиком, начало слова, внутри слова
own = parse_words("редиска, капуст*, *морков*")
expect("целиком", find_swear("ты редиска", own) is not None, True)
expect("не целиком", find_swear("редиски", own), None)
expect("начало", find_swear("капустный", own) is not None, True)
expect("с приставкой", find_swear("накапустил", own) is not None, True)
expect("внутри", find_swear("сверхморковный", own) is not None, True)
expect("пустой список", find_swear("сука", []), None)
expect("с новой строки", parse_words("сука\nбля; *пизд*"), ["сука", "бля", "*пизд*"])

# ---------- Сценарий в группе (нужна база) ----------
DB_URL = os.getenv("TEST_DATABASE_URL", "")


async def scenario():
    import types
    from database.database import engine, init_db, session_scope
    from database.models import ChatWarning
    from features import antimat
    from settings import store
    from sqlalchemy import delete

    await init_db()
    CHAT, USER = -100555000777, 7001
    async with session_scope() as session:
        await session.execute(delete(ChatWarning).where(ChatWarning.chat_id == CHAT))
        await session.commit()

    class Bot:
        def __init__(self):
            self.muted = []

        async def get_chat_member(self, chat_id, user_id):
            return types.SimpleNamespace(status="member")

        async def restrict_chat_member(self, chat_id, user_id, permissions, until_date):
            self.muted.append(user_id)

    bot = Bot()
    said, deleted = [], []

    def message(text, via_bot=None):
        async def answer(t):
            said.append(t)

        async def delete_():
            deleted.append(text)

        return types.SimpleNamespace(
            text=text, caption=None, bot=bot, message_id=len(said) + 1, via_bot=via_bot,
            chat=types.SimpleNamespace(id=CHAT, type="supergroup"),
            from_user=types.SimpleNamespace(id=USER, is_bot=False, first_name="Вася", username=None),
            answer=answer, delete=delete_,
        )

    async def swear(text):
        antimat._cooldown.clear()
        m = message(text)
        if antimat.is_swearing(m):
            await antimat.on_swear(m)

    # Выключен — молчит
    await swear("сука")
    expect("выключенный антимат молчит", said, [])

    store.apply(CHAT, "antimat", True)
    store.apply(CHAT, "antimat_words", DEFAULT_WORDS)
    store.apply(CHAT, "antimat_warnings", 3)
    store.apply(CHAT, "antimat_mute_minutes", 0)
    store.apply(CHAT, "antimat_notice_seconds", 0)

    # Срок не указан — только предупреждения 1/3, 2/3, 3/3, потом снова 1/3
    for word in ("сука", "бля", "нахуй", "пиздец"):
        await swear(word)
    expect("предупреждения без мута", [s.split("Предупреждение ")[1][:3] for s in said], ["1/3", "2/3", "3/3", "1/3"])
    expect("без срока мута нет", bot.muted, [])
    expect("сообщения с матом удалены", len(deleted), 4)
    await swear("обычный текст")
    expect("обычный текст не трогает", len(said), 4)
    # Предсказание через инлайн-бота: мат написал бот, человека не трогаем
    inline = message("Предсказание для @olesya: твой день пойдёт по пизде", via_bot=types.SimpleNamespace(id=99, is_bot=True))
    expect("инлайн-бот не считается", antimat.is_swearing(inline), False)

    # Админ указал 30 минут — на третьем предупреждении мут, счёт заново
    said.clear()
    store.apply(CHAT, "antimat_mute_minutes", 30)
    async with session_scope() as session:
        await session.execute(delete(ChatWarning).where(ChatWarning.chat_id == CHAT))
        await session.commit()
    for word in ("сука", "бля", "хуйня"):
        await swear(word)
    expect("два предупреждения, потом мут", ["мут" in s for s in said], [False, False, True])
    expect("мут на 30 минут", "30 мин" in said[-1], True)
    expect("замучен", bot.muted, [USER])
    await swear("сука")
    expect("после мута счёт заново", "1/3" in said[-1], True)
    # Второй мут за месяц — вдвое длиннее
    for word in ("бля", "хуйня"):
        await swear(word)
    expect("второй мут вдвое длиннее", "1 ч" in said[-1] and "вдвое" in said[-1], True)
    # Маскировка и умный словарь в группе: «бл@ть» тоже мат
    await swear("бл@ть")
    expect("маскировка в группе", "1/3" in said[-1], True)

    # Админ: по умолчанию тоже получает предупреждение; с выключенной настройкой — нет
    said.clear()
    async def admin_member(chat_id, user_id):
        return types.SimpleNamespace(status="administrator")
    bot.get_chat_member = admin_member
    antimat._admin_cache.clear()
    await swear("сука")
    expect("админ получил предупреждение", len(said) == 1 and "Предупреждение" in said[0], True)
    store.apply(CHAT, "antimat_admins", False)
    await swear("сука")
    expect("админов не трогать — молчит", len(said), 1)

    # Амнистия: Мара снимает муты за мат по журналу — только с тех, кто ещё замучен
    from database.models import AuditEvent
    from database.repository import add_audit

    async with session_scope() as session:
        await session.execute(delete(AuditEvent).where(AuditEvent.chat_id == CHAT))
        await session.commit()
    await add_audit("moderation", "mute", chat_id=CHAT, actor_kind="bot", target_id=USER, target_name="Вася", details="30 мин · мат, 3 предупреждения")
    await add_audit("moderation", "mute", chat_id=CHAT, actor_kind="bot", target_id=7002, target_name="Петя", details="30 мин · мат, 3 предупреждения")
    await add_audit("moderation", "mute", chat_id=CHAT, actor_kind="admin", target_id=7003, target_name="Коля", details=None)
    expect("в журнале — только муты Мары за мат", sorted(await antimat.antimat_muted(CHAT)), [USER, 7002])

    restricted = {USER}
    unmuted = []

    async def member_status(chat_id, user_id):
        muted = user_id in restricted
        return types.SimpleNamespace(status="restricted" if muted else "member", can_send_messages=not muted)

    async def get_chat(chat_id):
        return types.SimpleNamespace(permissions=None)

    async def restrict(chat_id, user_id, permissions, until_date=None):
        unmuted.append(user_id)

    bot.get_chat_member, bot.get_chat, bot.restrict_chat_member = member_status, get_chat, restrict
    freed, problems = await antimat.amnesty(bot, CHAT, clear_warnings=True)
    expect("снят мут только с замученного", (freed, unmuted, problems), (["Вася"], [USER], []))
    from database.repository import count_warnings_by_reason
    expect("предупреждения за мат обнулены", await count_warnings_by_reason(CHAT, USER, antimat.REASON), 0)
    expect("текст амнистии", "Вася" in antimat.amnesty_text(freed, True) and "заново" in antimat.amnesty_text(freed, True), True)

    # Слово, за которое мут, теперь в журнале
    antimat._cooldown.clear()
    await swear("/job ты сука")
    from sqlalchemy import select
    async with session_scope() as session:
        details = (await session.execute(select(AuditEvent.details).where(
            AuditEvent.chat_id == CHAT, AuditEvent.action == "warn").order_by(AuditEvent.id.desc()))).scalars().first()
    expect("в журнале слово, за которое предупреждение", details is not None and "мат: сука" in details, True)

    # Владельцу — список действующих мутов после обновления, с кнопкой на каждого
    from datetime import datetime
    from database.repository import get_group_settings, set_group_setting
    from settings import handler as owners

    restricted.clear()
    restricted.update({USER, 7002})
    sent = []

    async def send_message(chat_id, text, reply_markup=None, **kw):
        sent.append((chat_id, text, reply_markup))

    bot.send_message = send_message
    old_once, old_since, old_owners = antimat.AMNESTY_ONCE, antimat.AMNESTY_SINCE, owners.OWNER_IDS
    antimat.AMNESTY_ONCE, antimat.AMNESTY_SINCE = (CHAT,), "2000-01-01T00:00:00"
    owners.OWNER_IDS = frozenset({424242})
    saved = (await get_group_settings(0)).get(antimat.AMNESTY_DONE_KEY)
    await set_group_setting(chat_id=0, key=antimat.AMNESTY_DONE_KEY, value=[])
    try:
        await antimat.amnesty_once(bot)
        buttons = [b.callback_data for row in sent[0][2].inline_keyboard for b in row] if sent and sent[0][2] else []
        expect("список владельцу с кнопками", (sent[0][0], sorted(buttons)),
               (424242, sorted([f"amn:{CHAT}:{USER}", f"amn:{CHAT}:7002", f"amn:{CHAT}:all"])))
        await antimat.amnesty_once(bot)
        expect("список приходит один раз", len(sent), 1)

        # Кнопка «Снять мут» у одного: мут снят, его кнопка исчезает
        unmuted.clear()
        answers, edited = [], []

        async def cb_answer(text=None, show_alert=False):
            answers.append(text)

        async def edit_markup(reply_markup=None):
            edited.append(reply_markup)

        callback = types.SimpleNamespace(
            data=f"amn:{CHAT}:7002", from_user=types.SimpleNamespace(id=424242), bot=bot, answer=cb_answer,
            message=types.SimpleNamespace(reply_markup=sent[0][2], edit_reply_markup=edit_markup))
        await antimat.amnesty_button(callback)
        left = [b.callback_data for row in edited[-1].inline_keyboard for b in row]
        expect("снят мут одному", (unmuted, f"amn:{CHAT}:7002" in left), ([7002], False))
        callback.from_user = types.SimpleNamespace(id=1)
        await antimat.amnesty_button(callback)
        expect("чужому кнопка не работает", answers[-1], "Это только для владельца бота")
    finally:
        antimat.AMNESTY_ONCE, antimat.AMNESTY_SINCE = old_once, old_since
        owners.OWNER_IDS = old_owners
        await set_group_setting(chat_id=0, key=antimat.AMNESTY_DONE_KEY, value=saved)

    async with session_scope() as session:
        await session.execute(delete(ChatWarning).where(ChatWarning.chat_id == CHAT))
        await session.execute(delete(AuditEvent).where(AuditEvent.chat_id == CHAT))
        await session.commit()
    await engine.dispose()


if DB_URL:
    import asyncio
    asyncio.run(scenario())
else:
    print("ℹ️  TEST_DATABASE_URL не задан — сценарий с базой пропущен")

if failures:
    print(f"❌ Ошибок: {len(failures)} из {checks}")
    print("\n".join(failures))
    sys.exit(1)
print(f"✅ Все {checks} проверок антимата прошли.")
