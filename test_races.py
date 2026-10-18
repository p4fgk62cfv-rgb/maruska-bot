"""
Гонки при записи в базу и пропавшие модели нейросетей.

    python test_races.py                      — без базы: только модели
    TEST_DATABASE_URL=postgresql://… python test_races.py
"""

import asyncio
import os
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
DB_URL = os.getenv("TEST_DATABASE_URL", "")
os.environ.setdefault("DATABASE_URL", DB_URL or "postgresql+asyncpg://x:y@127.0.0.1:1/z")

from ai import fallback  # noqa: E402

errors, checks = [], 0


def check(ok, what):
    global checks
    checks += 1
    if not ok:
        errors.append(what)


groq = fallback.PROVIDERS[0]
os.environ.pop(groq.model_env, None)
check(not any("llama" in m or "qwen3-32b" in m for m in groq.default_models), "в списке Groq нет снятых моделей")
check(fallback._model_gone(404, '{"error":{"message":"The model `x` does not exist or you do not have access to it."}}'),
      "404 «модели нет» распознаётся")

fallback._gone.clear()
fallback._working.pop(groq.name, None)
first = groq.models[0]
fallback._gone[(groq.name, first)] = fallback.time.monotonic()
check(first not in groq.models, "пропавшую модель не пробуем сутки")
fallback._gone.update({(groq.name, m): fallback.time.monotonic() for m in groq.default_models})
check(groq.models == list(groq.default_models), "пропали все — пробуем все, вдруг вернулись")
fallback._gone.clear()


async def database():
    from database.database import init_db, session_scope
    from database.models import User, UserAchievement
    from database.repository import save_user, unlock_achievement
    from sqlalchemy import func, select

    await init_db()
    uid = random.randint(10**9, 2 * 10**9)

    await asyncio.gather(*[save_user(uid, "vasya", "Вася") for _ in range(10)])
    await save_user(uid, "vasya_new", "Василий")
    async with session_scope() as session:
        rows = (await session.execute(select(User).where(User.telegram_id == uid))).scalars().all()
    check(len(rows) == 1 and rows[0].username == "vasya_new", f"10 одновременных save_user — одна запись, обновлена: {len(rows)}")

    results = await asyncio.gather(*[unlock_achievement(uid, "first_message") for _ in range(10)])
    async with session_scope() as session:
        count = (await session.execute(select(func.count()).select_from(UserAchievement)
                                       .where(UserAchievement.telegram_id == uid))).scalar()
    check(results.count(True) == 1 and count == 1, f"достижение открыто ровно один раз: {results.count(True)}, {count}")


if DB_URL:
    asyncio.run(database())
else:
    print("   (без TEST_DATABASE_URL база не проверялась)")

if errors:
    print(f"❌ {len(errors)} из {checks} проверок не прошли:")
    print("\n".join("  " + e for e in errors))
    sys.exit(1)

print(f"✅ Все {checks} проверок гонок и моделей прошли.")
