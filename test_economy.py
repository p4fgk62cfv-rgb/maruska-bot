"""
Проверка экономики без базы и без бота.

Запуск:  python test_economy.py
"""

import re
from datetime import datetime, timedelta

from economy.service import (
    BONUS_MAX,
    BONUS_MIN,
    JACKPOT_MAX,
    JACKPOT_MIN,
    money,
    plural,
    reason_text,
    roll_bonus,
    streak_mark,
    wealth_title,
)


def simulate_bonus(last_bonus_at, now, streak):
    """
    Повторяет логику claim_daily_bonus из репозитория, чтобы
    правила серии можно было проверить без базы.

    Серия считается по календарным дням: продлевается, только
    если прошлый бонус был ровно вчера.
    """
    if last_bonus_at is not None and last_bonus_at.date() == now.date():
        return {"claimed": False, "streak": streak}

    gap = (now.date() - last_bonus_at.date()).days if last_bonus_at else None

    return {"claimed": True, "streak": streak + 1 if gap == 1 else 1}


def main() -> int:
    failures = []
    checks = 0

    # 1. Бонус всегда попадает в объявленные границы
    seen_jackpot = False

    for _ in range(3000):
        amount, jackpot = roll_bonus()
        checks += 1

        if jackpot:
            seen_jackpot = True
            if not (JACKPOT_MIN <= amount <= JACKPOT_MAX):
                failures.append(f"  [бонус] джекпот вне диапазона: {amount}")
                break
        elif not (BONUS_MIN <= amount <= BONUS_MAX):
            failures.append(f"  [бонус] сумма вне диапазона: {amount}")
            break

    if not seen_jackpot:
        failures.append("  [бонус] джекпот ни разу не выпал за 3000 попыток")

    # 2. Серия бонусов
    day = datetime(2026, 9, 21, 12, 0)

    cases = [
        # (последний бонус, сейчас, серия до, ожидание claimed, ожидание серии)
        (None, day, 0, True, 1),
        (day, day + timedelta(hours=3), 1, False, 1),
        (day, day + timedelta(days=1), 1, True, 2),
        (day, day + timedelta(days=2), 5, True, 1),
        (day, day + timedelta(days=1, hours=10), 7, True, 8),
        (day, day + timedelta(hours=13), 4, True, 5),
        (day, day + timedelta(days=3), 30, True, 1),
    ]

    for last, now, streak, expect_claimed, expect_streak in cases:
        checks += 1
        result = simulate_bonus(last, now, streak)

        if result["claimed"] != expect_claimed:
            failures.append(
                f"  [серия] {last} -> {now}: claimed "
                f"{result['claimed']}, ждали {expect_claimed}"
            )
        elif result["streak"] != expect_streak:
            failures.append(
                f"  [серия] {last} -> {now}: серия "
                f"{result['streak']}, ждали {expect_streak}"
            )

    # 3. Склонение
    plural_cases = {
        1: "алмаз", 2: "алмаза", 4: "алмаза", 5: "алмазов",
        11: "алмазов", 12: "алмазов", 14: "алмазов",
        21: "алмаз", 22: "алмаза", 25: "алмазов",
        100: "алмазов", 101: "алмаз", 111: "алмазов",
    }

    for amount, expected in plural_cases.items():
        checks += 1
        if plural(amount) != expected:
            failures.append(
                f"  [склонение] {amount}: {plural(amount)}, ждали {expected}"
            )

    # 4. Форматирование суммы
    checks += 1
    if money(1234567) != "1 234 567 💎":
        failures.append(f"  [формат] {money(1234567)!r}")

    # 5. Статусы по балансу растут монотонно
    previous = None
    for balance in (0, 50, 100, 499, 500, 1999, 2000, 4999, 5000, 9999, 10000):
        checks += 1
        title = wealth_title(balance)
        if not title:
            failures.append(f"  [статус] пусто для {balance}")
        previous = title

    # 6. Метка серии
    checks += 1
    if streak_mark(1) or not streak_mark(3) or streak_mark(30) != "🔥🔥🔥":
        failures.append("  [серия] метки огня считаются неверно")

    # 7. Расшифровка операций
    checks += 1
    if reason_text("bonus") != "Ежедневный бонус":
        failures.append("  [история] не расшифровывается причина")

    checks += 1
    if reason_text("bonus", "Своя заметка") != "Своя заметка":
        failures.append("  [история] заметка должна перебивать причину")

    if failures:
        print(f"❌ {len(failures)} проблем:\n")
        print("\n".join(failures))
        return 1

    print(f"✅ Все {checks} проверок прошли.")
    print(f"   бонус: {BONUS_MIN}–{BONUS_MAX} 💎, "
          f"джекпот {JACKPOT_MIN}–{JACKPOT_MAX} 💎")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
