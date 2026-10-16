"""
Игры в чате через кнопки: лобби, вызов, ходы, Маруська-соперник, реванш.
Telegram заменён заглушками. Запуск:  python test_table_chat.py
"""

import asyncio
import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import games.table as t  # noqa: E402

t.is_enabled = lambda chat_id, key: True
t.economy_on = lambda chat_id: False


async def _no_settle(game, winner):
    return ""


t.settle = _no_settle
errors = []


def check(ok, what):
    if not ok:
        errors.append(what)


class User:
    def __init__(self, uid, name):
        self.id, self.first_name, self.last_name, self.username, self.is_bot, self.full_name = uid, name, None, None, False, name


class Msg:
    sent = []

    def __init__(self, chat_id=-100, text="", user=None, reply=None):
        self.chat = types.SimpleNamespace(id=chat_id, type="private" if chat_id > 0 else "supergroup")
        self.text, self.from_user, self.reply_to_message = text, user, reply
        self.message_id = len(Msg.sent) + 1
        self.body, self.markup = "", None

    async def answer(self, text, reply_markup=None, **kw):
        m = Msg(self.chat.id)
        m.body, m.markup = text, reply_markup
        Msg.sent.append(m)
        return m

    async def edit_text(self, text, reply_markup=None, **kw):
        self.body, self.markup = text, reply_markup

    async def answer_photo(self, photo, caption="", reply_markup=None, **kw):
        assert photo.data[:2] == b"\xff\xd8", "не JPEG"
        m = await self.answer(caption, reply_markup=reply_markup)
        m.photo = photo
        return m

    async def edit_media(self, media, reply_markup=None, **kw):
        assert media.media.data[:2] == b"\xff\xd8", "не JPEG"
        self.body, self.photo = media.caption, media.media
        if reply_markup is not None:
            self.markup = reply_markup

    async def edit_caption(self, caption="", reply_markup=None, **kw):
        self.body = caption
        if reply_markup is not None:
            self.markup = reply_markup


class Cb:
    def __init__(self, user, message, data):
        self.from_user, self.message, self.data, self.alert = user, message, data, None

    async def answer(self, text=None, show_alert=False, **kw):
        self.alert = text


def buttons(m):
    return [b for row in (m.markup.inline_keyboard if m.markup else []) for b in row]


async def press(user, m, label_or_data):
    data = label_or_data if ":" in label_or_data else next(b.callback_data for b in buttons(m) if label_or_data in b.text)
    cb = Cb(user, m, data)
    if data.startswith("tg:"):
        await t.table_press(cb)
    elif data.startswith("tm:"):
        await t.menu_pick(cb)
    elif data.startswith("tc:"):
        await t.coin_press(cb)
    return cb


async def main():
    real_sleep = asyncio.sleep
    t.asyncio = types.SimpleNamespace(sleep=lambda *_: real_sleep(0), Lock=asyncio.Lock, to_thread=asyncio.to_thread)
    a, b, c = User(1, "Аня"), User(2, "Боря"), User(3, "Вася")

    # Крестики: открытый стол, Боря присоединяется, Вася не может ходить
    await t.table_command(Msg(text="/крестики", user=a))
    m = Msg.sent[-1]
    check("ищет соперника" in m.body, f"лобби: {m.body}")
    cb = await press(a, m, "Играю")
    check("Ждём соперника" in (cb.alert or ""), "сам с собой нельзя")
    await press(b, m, "Играю")
    check("Ходит" in m.body, f"старт: {m.body}")
    gid = buttons(m)[0].callback_data.split(":")[1]
    g = t._games[gid]
    first = g.players[g.turn][0]
    mover = a if first == 1 else b
    other = b if mover is a else a
    cb = await press(c, m, f"tg:{gid}:m:0")
    check("не в этой партии" in (cb.alert or ""), "чужой не ходит")
    cb = await press(other, m, f"tg:{gid}:m:0")
    check("не твой ход" in (cb.alert or ""), "не в свой ход")
    for cell, who in ((0, mover), (3, other), (1, mover), (4, other), (2, mover)):
        await press(who, m, f"tg:{gid}:m:{cell}")
    check("Побеждает" in m.body and g.status == "over", f"победа: {m.body}")
    await press(a, m, "Реванш")
    check(g.status == "playing" and g.state == [""] * 9, "реванш")

    # Вызов ответом: принять может только приглашённый
    await t.table_command(Msg(text="/шашки", user=a, reply=Msg(user=b)))
    m = Msg.sent[-1]
    check("вызывает" in m.body, "вызов")
    cb = await press(c, m, "Принять")
    check("не тебе" in (cb.alert or ""), "чужой вызов")
    await press(b, m, "Принять")
    gid = buttons(m)[0].callback_data.split(":")[1]
    g = t._games[gid]
    white = a if g.players[g.turn_white][0] == 1 else b
    black = b if white is a else a
    cb = await press(white, m, f"tg:{gid}:c:{5 * 8 + 0}")
    check(g.selected == 40, "выбор шашки")
    check(any(x.text == "🟩" for x in buttons(m)), "подсветка ходов")
    await press(white, m, f"tg:{gid}:c:{4 * 8 + 1}")
    check(g.state.turn == "b" and g.players[g.turn][0] == black.id, "ход перешёл")
    await press(black, m, "Сдаться")
    check(g.status == "over" and "сдаётся" in m.body, "сдача")

    # Шашки с Маруськой: доигрываем случайными ходами до конца
    await t.table_command(Msg(text="/шашки", user=a))
    m = Msg.sent[-1]
    await press(a, m, "С Маруськой")
    gid = buttons(m)[0].callback_data.split(":")[1]
    g = t._games[gid]
    for _ in range(400):
        if g.status != "playing":
            break
        opts = g.state.options()
        src = g.state.chain if g.state.chain is not None else next(iter(opts))
        if g.selected != src:
            await press(a, m, f"tg:{gid}:c:{src}")
        await press(a, m, f"tg:{gid}:c:{opts[src][0]}")
    check(g.status == "over", "партия с Маруськой не закончилась")

    # Морской бой с Маруськой
    await t.table_command(Msg(text="/морской", user=a))
    m = Msg.sent[-1]
    await press(a, m, "С Маруськой")
    gid = buttons(m)[0].callback_data.split(":")[1]
    g = t._games[gid]
    cb = await press(a, m, "Мои корабли")
    check(cb.alert and "■" in cb.alert and len(cb.alert) <= 200, f"флот: {cb.alert!r}")
    for pos in range(64):
        if g.status != "playing":
            break
        if pos not in g.state[1].shots:
            await press(a, m, f"tg:{gid}:s:{pos}")
    check(g.status == "over", "морской бой не закончился")

    # КНБ вдвоём: выбор скрыт до второго
    await t.table_command(Msg(text="/кнб", user=a))
    m = Msg.sent[-1]
    await press(b, m, "Играю")
    gid = buttons(m)[0].callback_data.split(":")[1]
    await press(a, m, f"tg:{gid}:r:rock")
    check("Ждём" in m.body and "🪨" not in m.body, "выбор скрыт")
    await press(b, m, f"tg:{gid}:r:scissors")
    check("Побеждает <b>Аня</b>" in m.body, f"кнб итог: {m.body}")

    # Орёл или решка: автор выбирает сторону, соперник берёт другую
    await t.table_command(Msg(text="/орел", user=a))
    m = Msg.sent[-1]
    check("выбери свою сторону" in m.body, f"монетка: {m.body}")
    cb = await press(b, m, "Орёл")
    check("выбирает тот, кто начал" in (cb.alert or ""), "сторону выбирает автор")
    gid = buttons(m)[0].callback_data.split(":")[1]
    cb = await press(b, m, f"tc:{gid}:join:")
    check("Сначала" in (cb.alert or ""), "до выбора стороны нельзя присоединиться")
    await press(a, m, "Решка")
    check("за решку" in m.body and any("Играю за орла" in x.text for x in buttons(m)), f"сторона: {m.body}")
    cb = await press(a, m, "Играю")
    check("Ждём соперника" in (cb.alert or ""), "сам с собой нельзя")
    await press(b, m, "Играю")
    check(("Выпал орёл" in m.body or "Выпала решка" in m.body) and "Победа за" in m.body, f"итог монетки: {m.body}")
    check("Боря" in m.body and "Аня" in m.body, "оба игрока в итоге")
    cb = await press(a, m, "Ещё раз")
    check("выбери свою сторону" in Msg.sent[-1].body, "ещё раз")

    # Вызов ответом: принять может только приглашённый; или против Маруськи
    await t.table_command(Msg(text="/орел", user=a, reply=Msg(user=b)))
    m = Msg.sent[-1]
    await press(a, m, "Орёл")
    check("Принять (решка)" in buttons(m)[0].text, "кнопка приглашённому")
    cb = await press(c, m, "Принять")
    check("не тебе" in (cb.alert or ""), "чужой вызов монетки")
    await press(a, m, "Против Маруськи")
    check("Маруська" in m.body and "Победа за" in m.body, f"против Маруськи: {m.body}")

    # В личке — сразу против Маруськи после выбора стороны
    await t.table_command(Msg(chat_id=5, text="/орел", user=a))
    m = Msg.sent[-1]
    await press(a, m, "Орёл")
    check("Победа за" in m.body, f"монетка в личке: {m.body}")

    # Меню и личка
    await t.table_command(Msg(text="/игры", user=a))
    check("Игры Маруськи" in Msg.sent[-1].body, "меню")
    await t.table_command(Msg(chat_id=5, text="/крестики", user=a))
    check("Маруська" in Msg.sent[-1].body and "Ходит" in Msg.sent[-1].body or "Побеждает" in Msg.sent[-1].body, "в личке сразу с ботом")

    # Все данные кнопок влезают в 64 байта
    for m in Msg.sent:
        for x in buttons(m):
            check(len(x.callback_data.encode()) <= 64, f"длинные данные {x.callback_data}")


asyncio.run(main())
if errors:
    print("❌ " + "\n❌ ".join(errors[:20]))
    sys.exit(1)
print("✅ Игры в чате: лобби, ходы, бот и реванш работают.")
