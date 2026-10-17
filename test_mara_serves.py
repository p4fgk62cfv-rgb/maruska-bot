"""
«Мара, кофе», «кофе @ник» и «Мара, покажи @ник».
Запуск:  python test_mara_serves.py
"""

import os
import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).parent))
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:y@127.0.0.1:1/z")

import botcontext  # noqa: E402
from actions.catalog import find_action  # noqa: E402
from actions.handler import mara_serves  # noqa: E402
from actions.show_me import is_show_other  # noqa: E402

errors = []


def check(ok, what):
    if not ok:
        errors.append(what)


# Распознавание действия
for text, key in {
    "кофе": "coffee", "Мара, кофе": "coffee", "Мара кофе": "coffee", "Маруся, обними": "hug",
    "кофе @vasya_99": "coffee", "@vasya пиво": "beer", "Мара, принеси кофе": "coffee",
}.items():
    found = find_action(text)
    check(found is not None and found.key == key, f"{text!r} → {found.key if found else None}")
for text in ("Мара, как дела", "кофе вкусный был сегодня", "мара", "Марат кофе пьёт с утра"):
    check(find_action(text) is None, f"лишнее действие: {text!r}")

# Когда Маруська угощает сама
botcontext.BOT_ID = 777


def msg(text, reply_id=None):
    reply = types.SimpleNamespace(from_user=types.SimpleNamespace(id=reply_id, is_bot=reply_id == 777)) if reply_id else None
    return types.SimpleNamespace(text=text, reply_to_message=reply)


check(mara_serves(msg("Мара, кофе")), "Мара, кофе → угощает Мара")
check(mara_serves(msg("кофе", reply_id=777)), "кофе ответом Маре → угощает Мара")
check(not mara_serves(msg("кофе")), "просто кофе — не Мара")
check(not mara_serves(msg("Мара, кофе @vasya")), "с @ником — угощают vasya, а не автора")
check(not mara_serves(msg("Мара, кофе", reply_id=5)), "ответом человеку — угощают его")

# Фильтр действия: когда срабатывает и почему молчит
from actions.handler import _skip_reason  # noqa: E402


def gmsg(text, reply_id=None, reply_bot=False, author=1):
    reply = types.SimpleNamespace(from_user=types.SimpleNamespace(id=reply_id, is_bot=reply_bot)) if reply_id else None
    return types.SimpleNamespace(text=text, reply_to_message=reply, chat=types.SimpleNamespace(id=-100, type="supergroup"),
                                 from_user=types.SimpleNamespace(id=author, is_bot=False))


check(_skip_reason(gmsg("Кофе", reply_id=2)) is None, "ответом человеку «Кофе» срабатывает")
check(_skip_reason(gmsg("кофе", reply_id=777, reply_bot=True)) is None, "ответом Маре — Мара угощает")
check("нет адресата" in (_skip_reason(gmsg("кофе")) or ""), "просто «кофе» — нет адресата")
check("своё" in (_skip_reason(gmsg("кофе", reply_id=1)) or ""), "ответ на своё сообщение")
check("другого бота" in (_skip_reason(gmsg("кофе", reply_id=55, reply_bot=True)) or ""), "ответ другому боту")

# Котик-портрет другого человека
check(is_show_other("Мара, покажи @vasya", True), "покажи @ник")
check(is_show_other("Мара, покажи его", True), "покажи его ответом")
check(not is_show_other("Мара, покажи меня", True), "покажи меня — свой портрет")
check(not is_show_other("Мара, покажи погоду в Киеве завтра", True), "покажи погоду — не котик")
check(not is_show_other("Мара, покажи @vasya", False), "без адресата — нет")

if errors:
    print("❌ " + "\n❌ ".join(errors))
    sys.exit(1)
print("✅ Мара угощает сама, «кофе @ник» и «покажи @ник» работают.")
