"""
Проверка личности Мары, предсказаний и магазина.

Запуск:  python test_features.py
"""

import fortune

from ai.personas import DEFAULT_PERSONA, PERSONA_BY_KEY, PERSONAS, get_persona
from ai.prompts import build_prompt

from economy.shop import CATEGORIES, ITEMS, by_category, find

from progress.achievements import ACHIEVEMENTS, check
from progress.xp import bar, level_from_xp, progress, xp_for_level


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

    # Спрашивать можно сколько угодно, но без повторов подряд
    fortune.reset_history()
    checks += 1

    bodies = [
        fortune.predict(111, "Стас").split("\n\n")[1]
        for _ in range(fortune.HISTORY_SIZE)
    ]

    if len(set(bodies)) != len(bodies):
        failures.append("  [предсказание] повтор до исчерпания истории")

    # Имя подставляется, разметка целая
    checks += 1
    first = fortune.predict(111, "Стас")

    if "Стас" not in first or first.count("<b>") != first.count("</b>"):
        failures.append("  [предсказание] проблема с именем или разметкой")

    # Больше нет ограничения «одно в день, приходи завтра».
    # Само слово «завтра» в предсказании допустимо («Завтра поймёшь зачем»),
    # поэтому ищем формулировки ограничения — и во ВСЕХ вариантах, а не в одном
    # случайном: иначе тест падал раз в ~50 прогонов.
    limit_words = ("приходи завтра", "возвращайся завтра", "завтра снова", "завтра можно",
                   "уже получал", "уже получила", "раз в день", "одно в день")

    for text in tuple(fortune.FUNNY) + tuple(fortune.SERIOUS) + tuple(fortune.INTROS):
        checks += 1
        if any(word in text.lower() for word in limit_words):
            failures.append(f"  [предсказание] осталось ограничение по дням: {text[:60]}")

    # Оба вида предсказаний встречаются
    checks += 1
    fortune.reset_history()
    seen_funny = seen_serious = False

    for user_id in range(300):
        body = fortune.predict(user_id, "X").split("\n\n")[1]
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

    # =====================================================
    # Опыт и уровни
    # =====================================================

    checks += 1
    if level_from_xp(0) != 1 or xp_for_level(1) != 0:
        failures.append("  [опыт] стартовый уровень неверный")

    # Уровень монотонно растёт вместе с опытом
    previous = 0
    for xp in range(0, 60000, 137):
        level = level_from_xp(xp)
        checks += 1

        if level < previous:
            failures.append(f"  [опыт] уровень упал на {xp} xp")
            break

        previous = level

    # Порог уровня строго возрастает
    for level in range(1, 60):
        checks += 1
        if xp_for_level(level + 1) <= xp_for_level(level):
            failures.append(f"  [опыт] порог не растёт на уровне {level}")
            break

    # Прогресс внутри уровня согласован
    for xp in (0, 99, 100, 101, 5000, 99999):
        checks += 1
        data = progress(xp)

        if not 0 <= data["percent"] <= 100:
            failures.append(f"  [опыт] процент вне диапазона при {xp}")

        if data["into_level"] < 0 or data["left"] < 0:
            failures.append(f"  [опыт] отрицательные значения при {xp}")

        if xp_for_level(data["level"]) > xp:
            failures.append(f"  [опыт] уровень завышен при {xp}")

    checks += 1
    if len(bar(0)) != len(bar(100)) or "█" in bar(0) or "░" in bar(100):
        failures.append("  [опыт] полоска прогресса рисуется неверно")

    # =====================================================
    # Достижения
    # =====================================================

    keys = [item.key for item in ACHIEVEMENTS]
    checks += 1

    if len(keys) != len(set(keys)):
        failures.append("  [достижения] дубли ключей")

    for item in ACHIEVEMENTS:
        checks += 1

        if item.reward <= 0:
            failures.append(f"  [достижения] награда {item.reward} у {item.key}")

        if not item.title or not item.description:
            failures.append(f"  [достижения] пустое описание у {item.key}")

    # На пустой статистике не должно открываться ничего
    checks += 1
    if check({}, set()):
        failures.append("  [достижения] открываются на пустой статистике")

    # Первое сообщение открывает ровно одно достижение
    checks += 1
    opened = check({"messages": 1, "level": 1}, set())

    if [item.key for item in opened] != ["first_words"]:
        failures.append(
            f"  [достижения] первое сообщение открыло {[i.key for i in opened]}"
        )

    # Уже открытые не предлагаются повторно
    checks += 1
    if check({"messages": 1}, {"first_words"}):
        failures.append("  [достижения] предлагаются уже открытые")

    # Сильная статистика открывает много, но не всё (есть секретные)
    checks += 1
    strong = {
        "messages": 9999, "level": 30, "coins": 20000, "karma": 100,
        "games_won": 60, "best_streak": 40, "bonus_days": 40,
        "gifts_sent": 20, "likes": 20, "items": 30,
    }
    opened = check(strong, set())

    if len(opened) != len(ACHIEVEMENTS) - 1:
        failures.append(
            f"  [достижения] открылось {len(opened)} из {len(ACHIEVEMENTS)}, "
            "ждали все кроме секретного"
        )

    checks += 1
    if not check({**strong, "night_bonus": True}, set()):
        failures.append("  [достижения] секретное не открывается")

    if failures:
        print(f"❌ {len(failures)} проблем:\n")
        print("\n".join(failures))
        return 1

    print(f"✅ Все {checks} проверок прошли.")
    print(f"   характеров: {len(PERSONAS)}, "
          f"предсказаний: {len(fortune.FUNNY) + len(fortune.SERIOUS)}, "
          f"товаров: {len(ITEMS)}, "
          f"достижений: {len(ACHIEVEMENTS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
