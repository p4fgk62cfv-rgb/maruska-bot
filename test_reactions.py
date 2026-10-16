"""
Реакции Мары: что на что ставится и что все эмодзи разрешены Telegram.
Запуск:  python test_reactions.py
"""

import asyncio
import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import features.reactions as r  # noqa: E402
from actions.catalog_data import ACTIONS  # noqa: E402

# Список реакций, которые Telegram разрешает ботам (ReactionTypeEmoji)
ALLOWED = set(
    "👍 👎 ❤ 🔥 🥰 👏 😁 🤔 🤯 😱 🤬 😢 🎉 🤩 🤮 💩 🙏 👌 🕊 🤡 🥱 🥴 😍 🐳 ❤‍🔥 🌚 🌭 💯 🤣 ⚡ 🍌 🏆 💔 🤨 😐 🍓 🍾 💋 🖕 😈 😴 😭 "
    "🤓 👻 👨‍💻 👀 🎃 🙈 😇 😨 🤝 ✍ 🤗 🫡 🎅 🎄 ☃ 💅 🤪 🗿 🆒 💘 🙉 🦄 😘 💊 🙊 😎 👾 🤷‍♂ 🤷 🤷‍♀ 😡".split()
)

errors = []


def check(ok, what):
    if not ok:
        errors.append(what)


used = set(r.PAIR_DEFAULT) | set(r.PHOTO)
for options in list(r.ACTION_CATEGORY.values()) + list(r.ACTION_KEY.values()):
    used |= set(options)
for *options, _ in r.TEXT_RULES:
    used |= set(options)
check(not used - ALLOWED, f"запрещённые реакции: {used - ALLOWED}")

keys = {a.key for a in ACTIONS}
check(not set(r.ACTION_KEY) - keys, f"неизвестные ключи: {set(r.ACTION_KEY) - keys}")
for a in ACTIONS:
    check(r.pick_for_action(a) is not None, f"нет реакции на {a.key}")

by_key = {a.key: a for a in ACTIONS}
check(r.pick_for_action(by_key["vodka"]) in ("🥴", "🍾", "😈"), "водка")
check(r.pick_for_action(by_key["rose"]) in ("🥰", "😍", "💘"), "цветы")

LAUGHS = ("ахахах", "Хахаха 😂", "ржу не могу", "я ору", "лол", "пхпхпх", "ну ты даёшь)))", "АХАХ")
for t in LAUGHS:
    check(r.pick_for_text(t) in ("🤣", "😁"), f"смех: {t}")
for t in ("какой милый котик", "люблю вас ❤", "ты солнышко"):
    check(r.pick_for_text(t) in ("❤", "🥰", "😍"), f"милое: {t}")
check(r.pick_for_text("Поздравляю с днём рождения!") in ("🎉", "🍾", "👏"), "поздравление")
check(r.pick_for_text("мне так грустно") in ("🤗", "❤", "🙏"), "грусть")
check(r.pick_for_text("спокойной ночи всем") in ("😴", "🌚", "😇"), "ночь")
for t in ("привет, как дела", "завтра на работу", "хорошо", "кто идёт в кино", "харьков", "хахаль"):
    check(r.pick_for_text(t) is None, f"лишняя реакция: {t}")


# Мидлварь: ставит реакцию в группе, не ставит у ботов и в личке
class Msg:
    def __init__(self, text, chat_id=-100, bot=False, reply=None):
        self.text, self.caption, self.photo, self.video, self.animation = text, None, None, None, None
        self.chat = types.SimpleNamespace(id=chat_id, type="supergroup" if chat_id < 0 else "private")
        self.from_user = types.SimpleNamespace(id=1, is_bot=bot)
        self.reply_to_message = reply
        self.reactions = []

    async def react(self, reaction):
        self.reactions.append(reaction[0].emoji)


r.Message = Msg
r.is_enabled = lambda chat, key: True
r.get_number = lambda chat, key: 100
r.random.uniform = lambda a, b: 0


async def main():
    mw = r.ReactionsMiddleware()

    async def handler(event, data):
        return "ok"

    replied = Msg("x", reply=None)
    replied.from_user = types.SimpleNamespace(id=2, is_bot=False)
    cases = [
        (Msg("ахахах ну ты дал"), True, -101),
        (Msg("водка", reply=replied), True, -102),
        (Msg("ахахах", bot=True), False, -103),
        (Msg("ахахах", chat_id=5), False, 5),
        (Msg("привет"), False, -104),
    ]
    for m, want, chat in cases:
        m.chat.id = chat
        check(await mw(handler, m, {}) == "ok", "мидлварь вернула результат")
        await asyncio.sleep(0.01)
        check(bool(m.reactions) == want, f"реакция на {m.text!r} ({chat}): {m.reactions}")
    # Пауза между реакциями в одном чате
    a, b = Msg("ахах"), Msg("хахаха")
    a.chat.id = b.chat.id = -200
    await mw(handler, a, {})
    await mw(handler, b, {})
    await asyncio.sleep(0.01)
    check(a.reactions and not b.reactions, "реакции чаще паузы")


asyncio.run(main())

if errors:
    print("❌ " + "\n❌ ".join(errors[:30]))
    sys.exit(1)
print("✅ Реакции Мары: все проверки прошли.")
