"""
«Мара, покажи меня» — случайный котик как портрет собеседника.

Каждое настроение — отдельная коллекция, поэтому котики не
повторяются и не сводятся к одному типу снимка.
"""

import random

from actions.catalog_data import Action


def _mood(key: str, search: str, tags: str) -> Action:
    return Action(
        key=key,
        emoji="🐱",
        search=search,
        aliases=(),
        category="solo",
        tags=tuple(tags.split("|")),
    )


CAT_MOODS = (
    _mood("cat_funny", "cat funny face", "cat|kitten"),
    _mood("cat_sleepy", "cat sleeping lazy", "cat|kitten"),
    _mood("cat_grumpy", "cat grumpy serious", "cat|kitten"),
    _mood("cat_surprised", "cat surprised eyes", "cat|kitten"),
    _mood("cat_fluffy", "kitten fluffy cute", "cat|kitten"),
    _mood("cat_box", "cat box hiding", "cat|kitten"),
    _mood("cat_window", "cat window sitting", "cat|kitten"),
    _mood("cat_glasses", "cat glasses costume", "cat|kitten"),
    _mood("cat_stretch", "cat stretching yawn", "cat|kitten"),
    _mood("cat_hunter", "cat hunting grass", "cat|kitten"),
)


CAPTIONS = (
    "🐱 {name} сегодня выглядит примерно так",
    "🐱 Вот он, настоящий {name}. Без фильтров",
    "🐱 {name} после рабочей недели",
    "🐱 Фоторобот составлен. {name}, узнаёшь себя?",
    "🐱 {name} изнутри. Снаружи вроде приличный человек",
    "🐱 Так {name} выглядит до первой чашки кофе",
    "🐱 Официальный портрет. {name}, можно в рамочку",
    "🐱 {name}, когда в чате пишут что-то умное",
    "🐱 Нашла твоё фото, {name}. Не благодари",
    "🐱 {name} на переговорах. Ничего не уступит",
    "🐱 {name} в 7 утра. Сходство поразительное",
    "🐱 Вот это энергия, {name}. Держи портрет",
)


TRIGGERS = (
    "покажи меня",
    "покажи мене",
    "какой я",
    "какая я",
    "кто я",
    "мой портрет",
    "мое фото",
    "моё фото",
)


def is_show_me(text: str | None) -> bool:
    if not text:
        return False

    lowered = " ".join(text.lower().replace("ё", "е").split())

    return any(
        trigger.replace("ё", "е") in lowered
        for trigger in TRIGGERS
    )


def pick_mood() -> Action:
    return random.choice(CAT_MOODS)


def pick_caption(name: str) -> str:
    return random.choice(CAPTIONS).format(name=name)
