"""
Запасной мозг: когда у Gemini кончился лимит, отвечает другая нейросеть.
Сеть не нужна — оба сервиса подменены заглушками.
Запуск:  python test_ai_fallback.py
"""

import asyncio
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
os.environ.setdefault("GEMINI_API_KEY", "test")

import ai.gemini as gemini  # noqa: E402
import ai.fallback as fallback  # noqa: E402
import ai.router as router  # noqa: E402

errors = []


def check(ok, what):
    if not ok:
        errors.append(what)


class Quota(Exception):
    pass


calls = {"gemini": 0, "fallback": 0}
mode = {"gemini": "ok"}


async def fake_gemini(prompt, use_search=False, persona=None):
    calls["gemini"] += 1
    if mode["gemini"] == "quota":
        raise Quota("429 RESOURCE_EXHAUSTED: quota exceeded")
    if mode["gemini"] == "down":
        raise TimeoutError("timed out")
    return "ответ Gemini", []


async def fake_fallback(system, prompt, temperature, max_tokens):
    calls["fallback"] += 1
    check("Маруськ" in system or system, "системный промпт передан")
    return "ответ Groq", "Groq"


gemini.ask_gemini = fake_gemini
fallback.ask_fallback = fake_fallback


async def main():
    # Без ключей запасных — ведём себя как раньше
    for key in ("GROQ_API_KEY", "OPENROUTER_API_KEY"):
        os.environ.pop(key, None)
    check(await router.ask_ai("привет") == "ответ Gemini", "обычный ответ Gemini")
    mode["gemini"] = "quota"
    try:
        await router.ask_ai("привет")
        check(False, "без запасной ошибка должна пробрасываться")
    except Quota:
        pass
    router._paused_until = 0

    # С ключом Groq — незаметное переключение
    os.environ["GROQ_API_KEY"] = "test"
    check(await router.ask_ai("привет") == "ответ Groq", "лимит → Groq")
    check(router.gemini_paused(), "Gemini на паузе после лимита")
    before = calls["gemini"]
    check(await router.ask_ai("ещё") == "ответ Groq", "на паузе отвечает Groq")
    check(calls["gemini"] == before, "на паузе Gemini не спрашиваем")

    # Пауза прошла — снова Gemini
    router._paused_until = 0
    mode["gemini"] = "ok"
    check(await router.ask_ai("привет") == "ответ Gemini", "после паузы снова Gemini")

    # Gemini просто упала (не лимит) — Groq отвечает, но без паузы
    mode["gemini"] = "down"
    check(await router.ask_ai("привет") == "ответ Groq", "сбой → Groq")
    check(not router.gemini_paused(), "сбой без лимита не ставит паузу")
    check(router.stats["last"] == "Groq" and router.stats["fallback"] >= 3, f"статистика: {router.stats}")


asyncio.run(main())

# Чистка «мыслей» рассуждающих моделей и выбор провайдеров
check(fallback.clean("<think>хм</think> Привет!") == "Привет!", "убирает <think>")
check(fallback.clean("Привет <think>недодумала") == "Привет", "обрезает незакрытый <think>")
os.environ["OPENROUTER_API_KEY"] = "x"
check([p.name for p in fallback.configured()] == ["Groq", "OpenRouter"], "порядок: Groq, потом OpenRouter")
check(router.is_quota(Exception("429 Too Many Requests")) and not router.is_quota(TimeoutError("timeout")), "распознаёт лимит")

if errors:
    print("❌ " + "\n❌ ".join(errors))
    sys.exit(1)
print("✅ Запасной мозг: переключение при лимите работает.")
