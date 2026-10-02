"""Антимат: что считается матом, а что нет.  python test_antimat.py"""

import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "postgresql://unused@localhost/unused")

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

    def message(text):
        async def answer(t):
            said.append(t)

        async def delete_():
            deleted.append(text)

        return types.SimpleNamespace(
            text=text, caption=None, bot=bot, message_id=len(said) + 1,
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

    # Срок не указан — только предупреждения 1/3, 2/3, 3/3, потом снова 1/3
    for word in ("сука", "бля", "нахуй", "пиздец"):
        await swear(word)
    expect("предупреждения без мута", [s.split("Предупреждение ")[1][:3] for s in said], ["1/3", "2/3", "3/3", "1/3"])
    expect("без срока мута нет", bot.muted, [])
    expect("сообщения с матом удалены", len(deleted), 4)
    await swear("обычный текст")
    expect("обычный текст не трогает", len(said), 4)

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

    async with session_scope() as session:
        await session.execute(delete(ChatWarning).where(ChatWarning.chat_id == CHAT))
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
