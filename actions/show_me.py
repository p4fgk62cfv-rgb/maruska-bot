"""
«Мара, покажи меня» — случайный котик как портрет собеседника.

Каждое настроение — отдельная коллекция, поэтому котики не
повторяются и не сводятся к одному типу снимка.
"""

import random
import re
from collections import deque

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
    "🐱 {name} в кошачьей версии. Гладить по шёрстке",
    "🐱 {name}, когда миска пустая уже целых пять минут",
    "🐱 {name} сбрасывает чашку со стола. Просто потому что может",
    "🐱 Это {name} в 4 утра носится по квартире",
    "🐱 {name} сидит в коробке и считает, что так и надо",
    "🐱 {name} мурчит. Значит, день удался",
    "🐱 {name} охотится на лазерную точку. Счёт пока 0:1",
    "🐱 {name} точит когти о любимый диван хозяина",
    "🐱 {name} требует еду. Срочно. Громко",
    "🐱 Это {name} нашёл место на клавиатуре, пока кто-то работает",
    "🐱 {name} спит 18 часов в сутки и всё равно устал",
    "🐱 {name} увидел огурец. Доверие к миру подорвано",
    "🐱 {name} на подоконнике следит за голубями. Миссия важная",
    "🐱 {name} делает вид, что не слышит «кис-кис»",
    "🐱 {name}, когда пылесос включили без предупреждения",
    "🐱 Это {name} несёт подарок. Лучше не смотреть какой",
    "🐱 {name} занял тёплое место и не уступит",
    "🐱 {name} и закрытая дверь. Вечный конфликт",
    "🐱 {name} проснулся, поел и снова устал",
    "🐱 {name} в режиме «мур». Беспокоить разрешено только с вкусняшкой",
    "🐱 {name} нашёл солнечный квадратик на полу. Счастье есть",
    "🐱 Это {name} после купания. Обиду затаил надолго",
    "🐱 {name} у ветеринара. Улыбаемся и терпим",
    "🐱 {name} гоняет фантик уже второй час",
    "🐱 {name}: девять жизней, и все на диване",
    "🐱 {name}, когда в миске не тот корм",
    "🐱 {name} сидит в пакете. Пакет теперь занят",
    "🐱 {name} крадётся к холодильнику на мягких лапках",
    "🐱 {name} мяукнул один раз. Значит, это важно",
    "🐱 {name} лежит пузом кверху. Это ловушка",
    "🐱 Это {name} уронил ёлку. Не жалеет",
    "🐱 {name} сидит на чистом белье. Теперь оно с шерстью",
    "🐱 {name} в засаде за шторой. Ноги, берегитесь",
    "🐱 {name} мурлычет громче холодильника",
    "🐱 {name} смотрит в пустой угол. Видит что-то, чего не видим мы",
    "🐱 {name} топчет плед лапками. Месит тесто для уюта",
    "🐱 {name} опять на столе. Ему можно, он главный",
    "🐱 {name} в образе котика с характером",
    "🐱 {name} просит открыть дверь. Потом закрыть. Потом снова открыть",
    "🐱 {name} уснул в самой неудобной позе. Зато мило",
    "🐱 Это {name} вылизывается перед важной встречей",
    "🐱 {name}, когда коробку от холодильника выкинули",
    "🐱 {name} спрятался. Хвост не спрятался",
    "🐱 {name} помогает работать: лёг прямо на ноутбук",
    "🐱 {name} чихнул и сам испугался",
    "🐱 {name} охраняет миску от посягательств",
    "🐱 {name}: мягкие лапки, острый характер",
    "🐱 Пушистый, ленивый, гордый. Да, это {name}",
    "🐱 {name} гладится только по расписанию. Сейчас не по расписанию",
    "🐱 {name} в кошачьем дзене. Мур на всё",
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


# «Мара, покажи @vasya» или ответом: «Мара, покажи его»
OTHER_RE = re.compile(r"\bпокажи\b", re.IGNORECASE)
OTHER_WORDS = ("его", "ее", "её", "этого", "эту", "этого человека", "кто это")


def is_show_other(text: str | None, has_target: bool) -> bool:
    """«покажи» + адресат (ответ на сообщение или @ник), но не «покажи меня»."""
    if not text or is_show_me(text) or not OTHER_RE.search(text):
        return False
    lowered = text.lower()
    return has_target and ("@" in text or any(w in lowered.split() for w in OTHER_WORDS) or len(lowered.split()) <= 3)


def pick_mood() -> Action:
    return random.choice(CAT_MOODS)


# Недавние подписи не повторяем, пока не пройдёт хотя бы столько других
RECENT_CAPTIONS = 25
_recent: deque[str] = deque(maxlen=RECENT_CAPTIONS)


def pick_caption(name: str) -> str:
    fresh = [caption for caption in CAPTIONS if caption not in _recent]
    caption = random.choice(fresh or CAPTIONS)
    _recent.append(caption)
    return caption.format(name=name)
