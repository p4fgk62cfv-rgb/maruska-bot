"""
Расход нейросетей: подсчёт ответов, лимитов, ошибок и токенов по дням.

    python test_ai_usage.py                      — без базы: только распознавание лимита
    TEST_DATABASE_URL=postgresql://… python test_ai_usage.py
"""

import asyncio
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
DB_URL = os.getenv("TEST_DATABASE_URL", "")
os.environ.setdefault("DATABASE_URL", DB_URL or "postgresql+asyncpg://x:y@127.0.0.1:1/z")

from ai import usage  # noqa: E402

errors, checks = [], 0


def check(ok, what):
    global checks
    checks += 1
    if not ok:
        errors.append(what)


check(usage.is_limit("429"), "429 — лимит")
check(usage.is_limit(Exception("RESOURCE_EXHAUSTED: quota exceeded")), "quota — лимит")
check(not usage.is_limit(Exception("TimeoutError")), "таймаут — не лимит")
check(len(usage.today()) == 10, "день в формате ГГГГ-ММ-ДД")


async def database():
    import random

    from database.database import init_db
    from database.repository import ai_usage, bump_ai_usage

    await init_db()
    day = f"2099-01-{random.randint(10, 28)}"
    for outcome, tokens in [("ok", 1000), ("ok", 500), ("limit", 0), ("error", 0)]:
        await bump_ai_usage(day, "Groq", "gpt-oss-120b", outcome, tokens)
    await asyncio.gather(*[bump_ai_usage(day, "Gemini", "flash", "ok", 10) for _ in range(20)])

    rows = {r["provider"]: r for r in await ai_usage(day, day)}
    g = rows.get("Groq", {})
    check(g.get("answers") == 2 and g.get("limits") == 1 and g.get("errors") == 1 and g.get("tokens") == 1500,
          f"Groq: {g}")
    check(g.get("last_limit_at") is not None, "время последнего лимита")
    check(rows.get("Gemini", {}).get("answers") == 20 and rows["Gemini"]["tokens"] == 200,
          f"одновременные ответы не теряются: {rows.get('Gemini')}")

    usage.record("OpenRouter", "nemotron", "ok", 42)
    await asyncio.sleep(0.5)
    check(any(r["provider"] == "OpenRouter" for r in await ai_usage(usage.today(), usage.today())),
          "record() пишет в базу в фоне")


if DB_URL:
    asyncio.run(database())
else:
    print("   (без TEST_DATABASE_URL база не проверялась)")

if errors:
    print(f"❌ {len(errors)} из {checks} проверок не прошли:")
    print("\n".join("  " + e for e in errors))
    sys.exit(1)

print(f"✅ Все {checks} проверок расхода нейросетей прошли.")
