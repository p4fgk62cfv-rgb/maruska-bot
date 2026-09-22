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
    "созвонимся в пятницу вечером",
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



# Новые действия
SHOULD_MATCH.update({
    # намерение глаголом действия — по-прежнему команда
    "Угости пивом": "beer",
    "Налей водки": "vodka",
    "Подари цветы": "flowers",
    "Вызвал дурку": "madhouse",
    "Держи кофе": "coffee",
    "Самогон": "moonshine",
    "Глинтвейн": "mulled_wine",
    "Мохито": "mojito",
    "Энергетик": "energy",
    "Какао": "cocoa",
    "Квас": "kvass",
    "Шаурма": "shawarma",
    "Борщ": "borscht",
    "Пельмени": "dumplings",
    "Сырники": "syrniki",
    "Попкорн": "popcorn",
    "Чизкейк": "cheesecake",
    "Пряник": "pryanik",
    "Жвачку": "gum",
    "Малина": "raspberry",
    "Хурма": "persimmon",
    "Пионы": "peony",
    "Ромашки": "chamomile",
    "Кактус": "cactus",
    "Миллион": "money",
    "Носки": "socks",
    "Корону": "crown",
    "Наушники": "headphones",
    "Котика": "cat",
    "Щенка": "dog",
    "Хомяка": "hamster",
    "Дурку": "madhouse",
    "вызвал дурку": "madhouse",
    "Психушку": "madhouse",
    "Скорую": "ambulance",
    "Такси": "taxi",
    "Пожарных": "firefighters",
    "Обнимаю": "hug",
    "Целую": "kiss",
    "Поцеловал": "kiss",
    "На ручки": "carry",
    "Погладить": "pat",
    "Пощекотать": "tickle",
    "Разбудить": "wake",
    "Сфоткать": "photo",
    "Подмигнуть": "wink",
    "Похвалить": "praise",
    "Молодец": "praise",
    "Баня": "banya",
    "Рыбалка": "fishing",
    "Спортзал": "gym",
    "Селфи": "selfie",
    "Отпуск": "sea",
    "Перекур": "coffee_break",
})

# Обычная переписка — реакции быть не должно
SHOULD_NOT_MATCH.extend([
    # реплики, где ключевое слово вплетено в разговор
    "Тоже кошку",
    "тоже хочу торт",
    "мне тоже пиво",
    "я люблю кошек",
    "у меня кошка дома",
    "какой милый котик у тебя",
    "она пиво не пьет",
    "надо купить торт",
    "а что она показывает",
    "так себе пицца",
    "давай лучше пиццу закажем",
    "он мне цветы дарил",
    "я поехал домой уже",
    "пойду спать наверное",
    "пошли гулять вечером",
    "он молодой ещё совсем",
    "там было около сотни человек",
    "у меня корона не жмёт",
    "какой-то он кислый сегодня",
    "это просто смешно",
    "ну ты даёшь конечно",
    "завтра созвонимся",
])


def check_exclusions() -> list[str]:
    """
    Проверяем, что теги-исключения реально отсекают мусор,
    на котором мы уже спотыкались в чате.
    """
    import sys, types

    sys.modules.setdefault("httpx", types.ModuleType("httpx"))

    from actions.catalog import ACTION_BY_KEY
    from actions.catalog_data import excluded_tags, required_tags
    from actions.providers import matches_tags

    cases = [
        # (действие, теги фото, должно ли подойти)
        ("borscht", "soup noodle letters alphabet macaroni", False),
        ("borscht", "noodle soup macaroni bowl", False),
        ("borscht", "borscht beetroot soup bowl", True),
        ("cutlet", "burger hamburger fries fast food", False),
        ("cutlet", "cutlet meatball meat plate", True),
        ("pasta", "alphabet letters noodles", False),
        ("pasta", "pasta spaghetti italian", True),
        ("fries", "burger hamburger fries", False),
        ("fries", "fries potato snack", True),
        ("steak", "burger sandwich bun", False),
        ("steak", "steak beef grill", True),
        ("soup", "noodle macaroni alphabet letters", False),
        ("soup", "noodle soup bowl chicken", True),
        ("soup", "soup broth bowl vegetables", True),
        ("pizza", "pizza drawing illustration vector", False),
        ("pizza", "pizza cheese italian", True),
        ("beer", "beer logo sign poster", False),
        ("beer", "beer glass pub foam", True),
    ]

    problems = []

    for key, tags, expected in cases:
        action = ACTION_BY_KEY[key]

        got = matches_tags(
            tags,
            required_tags(action),
            excluded_tags(action),
        )

        if got != expected:
            problems.append(
                f"  [теги] {key}: фото «{tags}» -> {got}, ждали {expected}"
            )

    return problems


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

    failures.extend(check_exclusions())

    total = len(SHOULD_MATCH) + len(SHOULD_NOT_MATCH) + 18

    if failures:
        print(f"❌ {len(failures)} из {total} проверок не прошли:\n")
        print("\n".join(failures))
        return 1

    print(f"✅ Все {total} проверок прошли.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
