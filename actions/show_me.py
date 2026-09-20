"""
«Мара, покажи меня» — случайный котик как портрет собеседника.

Каждое настроение — отдельная коллекция, поэтому котики не
повторяются и не сводятся к одному типу снимка.
"""

import random

from actions.catalog_data import Action


# Отсекаем львов-тигров (у них тоже тег "cat"), собак,
# пустые студийные силуэты и рисунки.
CAT_EXCLUDE = (
    "lion|tiger|leopard|cheetah|panther|jaguar|lynx|wild|wildlife|"
    "safari|zoo|dog|puppy|drawing|illustration|vector|clipart|"
    "sketch|painting|logo|silhouette|statue|toy"
)

# Требуем не просто кота, а кота с выражением лица.
CAT_TAGS = "cat|kitten|kitty"


def _mood(key: str, search: str) -> Action:
    return Action(
        key=key,
        emoji="🐱",
        search=search,
        aliases=(),
        category="solo",
        tags=tuple(CAT_TAGS.split("|")),
        exclude=tuple(CAT_EXCLUDE.split("|")),
    )


# Запросы подобраны так, чтобы приходили выразительные кадры,
# а не каталожные портреты породистых кошек.
CAT_MOODS = (
    _mood("cat_funny", "cat funny face"),
    _mood("cat_grumpy", "cat grumpy angry"),
    _mood("cat_surprised", "cat surprised big eyes"),
    _mood("cat_yawn", "cat yawning mouth open"),
    _mood("cat_tongue", "cat tongue out"),
    _mood("cat_box", "cat in box"),
    _mood("cat_glasses", "cat sunglasses costume"),
    _mood("cat_paws", "cat paws up playing"),
    _mood("cat_upside", "cat lying upside down"),
    _mood("cat_hiding", "cat hiding peeking"),
    _mood("cat_stretch", "cat stretching lazy"),
    _mood("cat_curious", "cat curious head tilt"),
)


# "Мара, мяу" — просто котик, без привязки к собеседнику
MEOW_TRIGGERS = ("мяу", "мур", "мурр", "кис-кис", "кискис", "котик?")

MEOW_CAPTIONS = (
    "🐱 Мяу так мяу",
    "🐱 Держи котика",
    "🐱 Принесла. Гладить осторожно",
    "🐱 Кот дня",
    "🐱 Вот этот на тебя посмотрел и одобрил",
    "🐱 По заявкам трудящихся",
    "🐱 Мур-мур. Настроение поднято",
    "🐱 Этот пришёл сам, я не звала",
    "🐱 Котик выдан. Следующий через минуту",
    "🐱 Лучшее, что я нашла за сегодня",
)


def is_meow(text: str | None) -> bool:
    if not text:
        return False

    lowered = " ".join(text.lower().replace("ё", "е").split())

    return any(trigger in lowered for trigger in MEOW_TRIGGERS)


def pick_meow_caption() -> str:
    return random.choice(MEOW_CAPTIONS)


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
