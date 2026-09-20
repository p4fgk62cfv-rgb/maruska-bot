"""
Быстрая проверка распознавания действий.

Запуск:  python test_actions.py
Зависимостей не требует.
"""

from actions.catalog import find_action


# Должны СРАБОТАТЬ
SHOULD_MATCH = {
    "Пиво": "beer",
    "пивка": "beer",
    "Кофе": "coffee",
    "кофейку": "coffee",
    "Чай": "tea",
    "Водки": "vodka",
    "Вина": "wine",
    "Пиццу": "pizza",
    "Суши": "sushi",
    "Тако": "taco",
    "Розы": "rose",
    "Цветы": "flowers",
    "Букет": "flowers",
    "Подарок": "gift",
    "Обнять": "hug",
    "обнимашки": "hug",
    "Поцеловать": "kiss",
    "Дай пять": "highfive",
    "Поддержать": "support",
    "Поздравить": "congratulations",
    "Потанцевать": "dance",
    "Маруська, пиво": "beer",
    "ну давай кофе": "coffee",
    "обними её": "hug",
    "торт 🎂": "cake",
}

# Должны ПРОМОЛЧАТЬ (раньше ломали чат)
SHOULD_NOT_MATCH = [
    "От такой картинки можно в депрессии впасть",
    "Это точно",
    "А картинки рандомно с инета подбираются?",
    "Не совсем с интернета а с сервиса специального",
    "опять двадцать пять",
    "какой повод?",
    "это супер",
    "поехали на завод",
    "высокий такой мужик",
    "он громко смеялся",
    "я купил джинсы",
    "пошли на рыбалку в пятницу",
    "мясник с рынка",
    "розетка не работает",
    "цветной принтер",
    "около дома",
    "чайник кипит",
    "виновата во всём",
    "сокол летит",
    "такой себе план если честно",
    "/top",
    "/profile",
    "Маруська, как дела?",
    "Маруська расскажи анекдот",
    "спасибо большое!",
    "Пастух пасёт стадо",
    "блин, забыл",
]


def main() -> int:
    failures = []

    for text, expected in SHOULD_MATCH.items():
        action = find_action(text)
        got = action.key if action else None
        if got != expected:
            failures.append(f"  [нет реакции] {text!r}: ждали {expected}, получили {got}")

    for text in SHOULD_NOT_MATCH:
        action = find_action(text)
        if action is not None:
            failures.append(f"  [ложное срабатывание] {text!r} -> {action.key}")

    total = len(SHOULD_MATCH) + len(SHOULD_NOT_MATCH)

    if failures:
        print(f"❌ {len(failures)} из {total} проверок не прошли:\n")
        print("\n".join(failures))
        return 1

    print(f"✅ Все {total} проверок прошли.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
