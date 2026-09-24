"""
Проверка кубиков, болтливости и итогов недели.

Запуск:  python test_extras.py
"""

import pathlib
import re

ROOT = pathlib.Path(__file__).parent

from games.dice_core import (
    EIGHT_BALL,
    MAX_DICE,
    MAX_SIDES,
    parse_roll,
    roll,
)


def load_week_key():
    """
    Берём _week_key из репозитория без импорта модуля:
    он тянет sqlalchemy, которого в тестах может не быть.
    """
    import pathlib
    from datetime import datetime

    src = (
        pathlib.Path(__file__).parent / "database" / "repository.py"
    ).read_text(encoding="utf-8")

    start = src.index("def _week_key")
    end = src.index("# =========================================================")

    scope = {"utcnow": lambda: datetime(2026, 9, 21)}
    exec(src[start:end], scope)

    return scope["_week_key"]


def load_digest_helpers():
    import pathlib

    src = (
        pathlib.Path(__file__).parent / "features" / "digest.py"
    ).read_text(encoding="utf-8")

    start = src.index("def _plural_days")
    end = src.index("async def build_digest")

    scope = {}
    exec(src[start:end], scope)

    return scope["_plural_days"]


def main() -> int:
    failures = []
    checks = 0

    # =====================================================
    # Кубики
    # =====================================================

    parse_cases = [
        ("1d6", (1, 6, 0)),
        ("2d6", (2, 6, 0)),
        ("d20", (1, 20, 0)),
        ("3d20+5", (3, 20, 5)),
        ("2d10-3", (2, 10, -3)),
        ("2к6", (2, 6, 0)),        # кириллическая «к»
        ("2д6", (2, 6, 0)),        # и «д»
        (" 4 d 8 ", (4, 8, 0)),
        ("100d6", None),           # слишком много кубиков
        ("1d5000", None),          # слишком много граней
        ("0d6", None),
        ("1d1", None),
        ("абвгд", None),
        ("", None),
    ]

    for text, expected in parse_cases:
        checks += 1
        got = parse_roll(text)

        if got != expected:
            failures.append(
                f"  [кубики] {text!r}: {got}, ждали {expected}"
            )

    # Броски всегда в границах
    for sides in (2, 6, 20, 100, MAX_SIDES):
        checks += 1
        values = roll(MAX_DICE, sides)

        if len(values) != MAX_DICE:
            failures.append(f"  [кубики] не то число бросков для d{sides}")

        if any(value < 1 or value > sides for value in values):
            failures.append(f"  [кубики] значение вне диапазона для d{sides}")

    # За много бросков должны встретиться обе границы
    checks += 1
    values = roll(3000, 6)

    if min(values) != 1 or max(values) != 6:
        failures.append("  [кубики] распределение не покрывает границы")

    checks += 1
    if len(EIGHT_BALL) < 15:
        failures.append("  [шар] маловато ответов")

    # =====================================================
    # Неделя
    # =====================================================

    from datetime import datetime

    week_key = load_week_key()

    checks += 1
    if week_key(datetime(2026, 9, 21)) == week_key(datetime(2026, 9, 20)):
        failures.append("  [неделя] понедельник не начинает новую неделю")

    checks += 1
    if week_key(datetime(2026, 9, 21)) != week_key(datetime(2026, 9, 27)):
        failures.append("  [неделя] дни одной недели дали разные ключи")

    checks += 1
    if not re.match(r"^\d{4}-W\d{2}$", week_key(datetime(2026, 1, 1))):
        failures.append("  [неделя] неверный формат ключа")

    # Склонение дней
    plural_days = load_digest_helpers()

    day_cases = {
        1: "день", 2: "дня", 4: "дня", 5: "дней",
        11: "дней", 12: "дней", 21: "день", 22: "дня",
        25: "дней", 101: "день", 111: "дней",
    }

    for value, expected in day_cases.items():
        checks += 1
        if plural_days(value) != expected:
            failures.append(
                f"  [дни] {value}: {plural_days(value)}, ждали {expected}"
            )

    # =====================================================
    # Болтливость
    # =====================================================

    from settings.registry import CHOICE_BY_KEY

    checks += 1
    chattiness = CHOICE_BY_KEY.get("chattiness")

    if chattiness is None:
        failures.append("  [болтливость] настройка не зарегистрирована")
    else:
        values_seen = {option[0] for option in chattiness.options}

        if values_seen != {"quiet", "normal", "active", "fun"}:
            failures.append(f"  [болтливость] неожиданные варианты: {values_seen}")

        # Каждый режим должен реально обрабатываться в разговоре
        chat_source = (ROOT / "features" / "chat.py").read_text(encoding="utf-8")

        for mode in values_seen - {"normal"}:
            if f'"{mode}"' not in chat_source:
                failures.append(f"  [болтливость] режим {mode!r} есть в настройках, но chat.py его не обрабатывает")

        if chattiness.default != "normal":
            failures.append("  [болтливость] умолчание должно быть normal")

    if failures:
        print(f"❌ {len(failures)} проблем:\n")
        print("\n".join(failures))
        return 1

    print(f"✅ Все {checks} проверок прошли.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
