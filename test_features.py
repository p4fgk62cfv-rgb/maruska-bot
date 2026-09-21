"""
Проверка личности Мары, предсказаний и магазина.

Запуск:  python test_features.py
"""

from datetime import datetime, timedelta, timezone

import fortune

from ai.personas import DEFAULT_PERSONA, PERSONA_BY_KEY, PERSONAS, get_persona
from ai.prompts import build_prompt

from economy.shop import CATEGORIES, ITEMS, by_category, find


def main() -> int:
    failures = []
    checks = 0

    # =====================================================
    # Личность
    # =====================================================

    keys = [persona.key for persona in PERSONAS]
    checks += 1

    if len(keys) != len(set(keys)):
        failures.append("  [личность] дубли ключей")

    if DEFAULT_PERSONA not in PERSONA_BY_KEY:
        failures.append("  [личность] значение по умолчанию отсутствует")

    for persona in PERSONAS:
        checks += 1
        prompt = build_prompt(persona.key)

        if persona.prompt not in prompt:
            failures.append(f"  [личность] характер {persona.key} не попал в промпт")

        if "{persona}" in prompt:
            failures.append(f"  [личность] плейсхолдер не заменён у {persona.key}")

        if len(prompt) < 500:
            failures.append(f"  [личность] промпт подозрительно короткий: {persona.key}")

    # Неизвестный ключ не должен ронять сборку
    checks += 1
    if get_persona("ерунда").key != DEFAULT_PERSONA:
        failures.append("  [личность] неизвестный ключ не откатывается к умолчанию")

    checks += 1
    if get_persona(None).key != DEFAULT_PERSONA:
        failures.append("  [личность] None не откатывается к умолчанию")

    # Характеры должны отличаться друг от друга
    checks += 1
    prompts = {build_prompt(p.key) for p in PERSONAS}

    if len(prompts) != len(PERSONAS):
        failures.append("  [личность] какие-то характеры дают одинаковый промпт")

    # =====================================================
    # Предсказания
    # =====================================================

    day = datetime(2026, 9, 21, tzinfo=timezone.utc)

    trigger_cases = [
        ("Мара, предскажи", True),
        ("Мара предсказание", True),
        ("погадай мне", True),
        ("Мара, что меня ждет", True),
        ("я это предсказал ещё на прошлой неделе всем нам", False),
        ("обычное сообщение", False),
        ("/fortune", False),
    ]

    for text, expected in trigger_cases:
        checks += 1
        if fortune.mentions_fortune(text) != expected:
            failures.append(f"  [предсказание] триггер {text!r}: ждали {expected}")

    # Одно и то же в течение дня, разное в разные дни
    checks += 1
    first = fortune.predict(111, "Стас", day)

    if first != fortune.predict(111, "Стас", day):
        failures.append("  [предсказание] нестабильно в пределах дня")

    checks += 1
    if first == fortune.predict(111, "Стас", day + timedelta(days=1)):
        failures.append("  [предсказание] не меняется на следующий день")

    checks += 1
    if first == fortune.predict(222, "Люда", day):
        failures.append("  [предсказание] совпало у разных людей")

    # Имя подставляется, разметка целая
    checks += 1
    if "Стас" not in first or first.count("<b>") != first.count("</b>"):
        failures.append("  [предсказание] проблема с именем или разметкой")

    # Оба вида предсказаний встречаются
    checks += 1
    seen_funny = seen_serious = False

    for user_id in range(300):
        body = fortune.predict(user_id, "X", day).split("\n\n")[1]
        if body in fortune.FUNNY:
            seen_funny = True
        elif body in fortune.SERIOUS:
            seen_serious = True
        else:
            failures.append("  [предсказание] текст не из списков")
            break

    if not (seen_funny and seen_serious):
        failures.append("  [предсказание] встречается только один вид")

    # =====================================================
    # Магазин
    # =====================================================

    item_keys = [item.key for item in ITEMS]
    checks += 1

    if len(item_keys) != len(set(item_keys)):
        failures.append("  [магазин] дубли ключей товаров")

    for item in ITEMS:
        checks += 1

        if item.price <= 0:
            failures.append(f"  [магазин] цена {item.price} у {item.key}")

        if item.category not in CATEGORIES:
            failures.append(f"  [магазин] неизвестная категория у {item.key}")

        if not item.emoji or not item.title:
            failures.append(f"  [магазин] пустое оформление у {item.key}")

    # Каждая категория непустая
    for category in CATEGORIES:
        checks += 1
        if not by_category(category):
            failures.append(f"  [магазин] пустая категория {category}")

    # Поиск находит и по ключу, и по названию
    search_cases = [("роза", "flower"), ("flower", "flower"),
                    ("Дракон", "dragon"), ("мусор", "trash")]

    for query, expected in search_cases:
        checks += 1
        found = find(query)

        if found is None or found.key != expected:
            failures.append(
                f"  [магазин] поиск {query!r} дал "
                f"{found.key if found else None}, ждали {expected}"
            )

    checks += 1
    if find("такого нет") is not None or find("") is not None:
        failures.append("  [магазин] поиск находит несуществующее")

    if failures:
        print(f"❌ {len(failures)} проблем:\n")
        print("\n".join(failures))
        return 1

    print(f"✅ Все {checks} проверок прошли.")
    print(f"   характеров: {len(PERSONAS)}, "
          f"предсказаний: {len(fortune.FUNNY) + len(fortune.SERIOUS)}, "
          f"товаров: {len(ITEMS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
