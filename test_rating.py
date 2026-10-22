"""
Рейтинг: «+» и «спасибо» в ответ, пауза 5 минут, сообщения Мары исчезают через 10 секунд.

    python test_rating.py
"""

import asyncio
import os
import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).parent))
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:y@127.0.0.1:1/z")

from features import rating  # noqa: E402

errors = []


def check(ok, what):
    if not ok:
        errors.append(what)


# Что считается «спасибо»
for text, want in [("спасибо", True), ("Спасибо!", True), ("спс", True), ("спасибо большое 🙏", True),
                   ("благодарю", True), ("thanks", True), ("Мара, спасибо", False),
                   ("спасибо, но я завтра не смогу прийти к вам", False), ("привет", False), ("", False)]:
    check(rating.is_thanks(text) == want, f"«{text}» → {not want}")

check(rating.cooldown_text(5) == "5 мин." and rating.cooldown_text(120) == "2 ч.", "текст паузы")

rating.is_enabled = lambda chat_id, key: True
rating.get_number = lambda chat_id, key: 5 if key == "rating_cooldown_minutes" else 0
rating.NOTICE_TTL = 0.05


def user(uid, bot=False):
    return types.SimpleNamespace(id=uid, is_bot=bot, username=None, first_name=f"u{uid}", last_name=None, full_name=f"u{uid}")


class Sent:
    def __init__(self, text):
        self.text, self.deleted = text, False

    async def delete(self):
        self.deleted = True


def msg(text, sender, target):
    replies = []

    async def reply(text, **kwargs):
        sent = Sent(text)
        replies.append(sent)
        return sent

    m = types.SimpleNamespace(
        text=text, from_user=sender, chat=types.SimpleNamespace(id=-100, type="supergroup"),
        reply_to_message=types.SimpleNamespace(from_user=target) if target else None, reply=reply,
    )
    return m, replies


# Фильтр: «спасибо» — только в ответ человеку
check(rating.is_rating_message(msg("спасибо", user(1), user(2))[0]), "спасибо человеку — оценка")
check(not rating.is_rating_message(msg("спасибо", user(1), None)[0]), "спасибо без реплая — не оценка")
check(not rating.is_rating_message(msg("спасибо", user(1), user(9, bot=True))[0]), "спасибо боту — не оценка")
check(rating.is_rating_message(msg("+", user(1), None)[0]), "плюс")

votes, pauses = [], []


async def can_vote(giver_telegram_id, target_telegram_id, cooldown_minutes=None, **kw):
    pauses.append(cooldown_minutes)
    return not any(v == (giver_telegram_id, target_telegram_id) for v in votes)


async def add_vote(giver_telegram_id, target_telegram_id, amount, display_name=None):
    votes.append((giver_telegram_id, target_telegram_id))
    return 7


async def save_user(**kw):
    return None


rating.can_vote_rating = can_vote
rating.add_rating_vote = add_vote
rating.save_user = save_user


async def scenario():
    m, replies = msg("спасибо", user(1), user(2))
    await rating.rating_handler(m)
    check(len(replies) == 1 and "Спасибо" in replies[0].text and "+1" in replies[0].text, f"спасибо: {[r.text for r in replies]}")
    check(pauses == [5], f"пауза 5 минут: {pauses}")
    await asyncio.sleep(0.15)
    check(replies[0].deleted, "сообщение Мары удалено")

    # Повторное «спасибо» в паузе — молча, «+» — подсказка (и она тоже исчезает)
    m, replies = msg("спасибо", user(1), user(2))
    await rating.rating_handler(m)
    check(replies == [], "повтор спасибо — тишина")
    m, replies = msg("+", user(1), user(2))
    await rating.rating_handler(m)
    check(len(replies) == 1 and "5 мин" in replies[0].text, f"пауза: {[r.text for r in replies]}")
    await asyncio.sleep(0.15)
    check(replies[0].deleted, "подсказка о паузе удалена")

    # Себе: на «спасибо» молчит
    m, replies = msg("спасибо", user(3), user(3))
    await rating.rating_handler(m)
    check(replies == [], "спасибо себе — тишина")


asyncio.run(scenario())

if errors:
    print("❌ " + "\n❌ ".join(errors))
    sys.exit(1)
print("✅ Рейтинг: все проверки прошли.")
