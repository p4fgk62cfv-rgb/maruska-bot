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
    "🐱 {name} в режиме «не трогайте меня»",
    "🐱 {name}, когда сказали, что завтра выходной",
    "🐱 {name} проверяет, не написал ли кто в чат. В сотый раз",
    "🐱 Это {name} смотрит на цены в магазине",
    "🐱 {name} делает вид, что работает",
    "🐱 {name} слушает чужое голосовое на пять минут",
    "🐱 {name} в понедельник. Комментарии излишни",
    "🐱 Редкий кадр: {name} в хорошем настроении",
    "🐱 {name} ждёт, когда закипит чайник",
    "🐱 {name} после фразы «нам надо поговорить»",
    "🐱 Паспортное фото: {name}. Один в один",
    "🐱 {name} у холодильника в два часа ночи",
    "🐱 Так {name} читает мелкий шрифт в договоре",
    "🐱 {name} на диете. Вторые сутки. Держится из последних сил",
    "🐱 {name}, когда кто-то доел последний кусок пиццы",
    "🐱 Это {name} притворяется, что не видит сообщение",
    "🐱 {name} в пробке. Терпение на нуле",
    "🐱 Снимок со скрытой камеры: {name} дома",
    "🐱 {name} строит планы на выходные. План: лежать",
    "🐱 {name} на совещании, которое могло быть письмом",
    "🐱 {name}, когда будильник звонит в третий раз",
    "🐱 {name} в ожидании зарплаты",
    "🐱 {name} в день зарплаты. Ненадолго",
    "🐱 Найдено в архиве: детское фото {name}",
    "🐱 {name} — профессиональный лежебока. Диплом прилагается",
    "🐱 {name} мыслями в отпуске уже третий месяц",
    "🐱 {name} проигрывает в дурака и делает вид, что так задумано",
    "🐱 {name}, когда Мара отвечает не сразу",
    "🐱 Раскрыта тайна пропавших носков. Это {name}",
    "🐱 {name} охраняет свою тарелку. Не подходи",
    "🐱 Это {name} обдумывает гениальную идею. Пока безуспешно",
    "🐱 {name} в образе загадочной личности",
    "🐱 {name} просит «ещё пять минуточек»",
    "🐱 {name}, когда в магазине скидка 70%",
    "🐱 Это {name} после спортзала. Первого и последнего",
    "🐱 {name} в режиме энергосбережения",
    "🐱 {name} смотрит «ещё одну серию». Десятую по счёту",
    "🐱 Портрет кисти Маруськи. Модель — {name}",
    "🐱 {name} в очереди второй час",
    "🐱 {name} при виде горы грязной посуды",
    "🐱 {name} на фотосессии для обложки журнала",
    "🐱 {name} и звонок с незнакомого номера",
    "🐱 Так {name} реагирует на слово «уборка»",
    "🐱 {name} в три часа ночи думает о смысле жизни",
    "🐱 Это {name} считает дни до отпуска",
    "🐱 {name} в роли начальника. Строго, но мило",
    "🐱 {name} после слов «я быстро, на минутку»",
    "🐱 Так {name} выглядит, когда всё под контролем. Почти",
    "🐱 {name} в засаде. Ждёт, когда принесут вкусняшку",
    "🐱 Это {name} читает чат после недели отпуска",
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
