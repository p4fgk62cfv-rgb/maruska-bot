"""
Игры в чате и экономика: ставка переходит от проигравшего к победителю,
награды и дневной лимит за победы над Маруськой. База заменена словарём.
Запуск:  python test_table_economy.py
"""

import asyncio
import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).parent))

wallet = {1: 100, 2: 30}
log = []


async def get_balance(uid):
    return wallet.get(uid, 0)


async def change_balance(uid, amount, reason, note=None, chat_id=None, display_name=None, allow_negative=False):
    if wallet.get(uid, 0) + amount < 0:
        return False, wallet.get(uid, 0)
    wallet[uid] = wallet.get(uid, 0) + amount
    log.append((uid, amount, reason))
    return True, wallet[uid]


async def bump_game_stats(*a, **k):
    pass


sys.modules["database.repository"] = types.SimpleNamespace(get_balance=get_balance, change_balance=change_balance, bump_game_stats=bump_game_stats)

import games.table as t  # noqa: E402

t.is_enabled = lambda chat_id, key: key != "progress"
t.get_number = lambda chat_id, key: None
errors = []


def check(ok, what):
    if not ok:
        errors.append(what)


async def main():
    # Ставка 50: у проигравшего только 30 — забираем что есть, плюс награда победителю
    g = t.Game(gid="a", kind="checkers", chat_id=-1, players=[(1, "Аня"), (2, "Боря")], stake=50)
    text = await t.settle(g, 0)
    check(wallet[2] == 0 and wallet[1] == 100 + 30 + 15, f"ставка и награда: {wallet}")
    check("+30" in text and "+15" in text, f"подпись: {text}")
    # Ничья — никто ничего не платит
    before = dict(wallet)
    await t.settle(t.Game(gid="b", kind="sea", chat_id=-1, players=[(1, "Аня"), (2, "Боря")], stake=10), None)
    check(wallet == before, "ничья без денег")
    # Победы над Маруськой: половина награды и не больше 10 в день
    wallet[3] = 0
    for _ in range(12):
        await t.settle(t.Game(gid="c", kind="ttt", chat_id=-1, players=[(3, "Вася"), (t.BOT_ID, "Маруська")]), 0)
    check(wallet[3] == 10 * 7, f"лимит и половина: {wallet[3]}")
    # Победа Маруськи — никому ничего
    before = dict(wallet)
    await t.settle(t.Game(gid="d", kind="ttt", chat_id=-1, players=[(1, "Аня"), (t.BOT_ID, "Маруська")]), 1)
    check(wallet == before, "победа бота без денег")
    # Экономика выключена — ни ставок, ни наград
    t.is_enabled = lambda chat_id, key: key not in ("economy", "progress")
    before = dict(wallet)
    await t.settle(t.Game(gid="e", kind="checkers", chat_id=-1, players=[(1, "Аня"), (2, "Боря")], stake=10), 0)
    check(wallet == before, "без экономики")


asyncio.run(main())
if errors:
    print("❌ " + "\n❌ ".join(errors))
    sys.exit(1)
print("✅ Игры в чате: ставки, награды и лимиты считаются верно.")
