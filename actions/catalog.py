"""
Каталог действий.

Главное отличие от старой версии:
действие распознаётся ТОЛЬКО как короткая самостоятельная фраза,
а не как случайная подстрока внутри обычного сообщения.

Правила распознавания:

1. Сообщение разбивается на слова (буквы, без пунктуации).
2. Служебные слова ("а", "ну", "маруська", "плиз"...) отбрасываются.
3. Если значимых слов больше MAX_ACTION_WORDS — это не действие.
4. Алиас сравнивается с НАЧАЛОМ слова, хвост не длиннее ALIAS_TAIL.
5. Алиас с префиксом "=" требует точного совпадения слова целиком
   (для коротких и двусмысленных: "тако", "вода", "суп", "пять"...).
6. Стоп-лист BLACKLIST гасит заведомые ложные срабатывания.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Action:
    key: str
    emoji: str
    search: str
    aliases: tuple[str, ...]
    category: str
    item_acc: str = ""
    item_instr: str = ""


ACTIONS = [
    # НАПИТКИ
    Action("beer", "🍺", "beer glass cold", ("пив",), "drink", "пиво", "пивом"),
    Action("coffee", "☕", "coffee cup cozy", ("кофе", "кофейк", "латте", "капучин"), "drink", "кофе", "кофе"),
    Action("tea", "🍵", "tea cup cozy", ("=чай", "=чаю", "=чая", "=чаем", "чаёк", "чаек"), "drink", "чай", "чаем"),
    Action("wine", "🍷", "wine glass evening", ("=вино", "=вина", "=вину", "=вином", "винишк", "винца"), "drink", "вино", "вином"),
    Action("champagne", "🥂", "champagne toast celebration", ("шампан",), "drink", "шампанское", "шампанским"),
    Action("whiskey", "🥃", "whiskey glass", ("виски",), "drink", "виски", "виски"),
    Action("cognac", "🥃", "cognac glass", ("коньяк",), "drink", "коньяк", "коньяком"),
    Action("vodka", "🍸", "vodka shot glass", ("водк", "водочк"), "drink", "водку", "водкой"),
    Action("moonshine", "🥃", "moonshine alcohol homemade", ("брага", "брагу", "самогон"), "drink", "брагу", "брагой"),
    Action("rum", "🥃", "rum drink", ("=ром", "=рома", "=рому", "=ромом"), "drink", "ром", "ромом"),
    Action("gin", "🍸", "gin tonic", ("=джин", "=джина", "=джину", "=джином"), "drink", "джин", "джином"),
    Action("tequila", "🍹", "tequila shot", ("текил",), "drink", "текилу", "текилой"),
    Action("cocktail", "🍹", "cocktail bar colorful", ("коктейл",), "drink", "коктейль", "коктейлем"),
    Action("martini", "🍸", "martini cocktail", ("мартини",), "drink", "мартини", "мартини"),
    Action("juice", "🧃", "juice orange fresh", ("=сок", "=сока", "=соку", "=соком", "сочок"), "drink", "сок", "соком"),
    Action("cola", "🥤", "cola glass", ("кола", "колу", "колы", "колой"), "drink", "колу", "колой"),
    Action("lemonade", "🍋", "lemonade drink", ("лимонад",), "drink", "лимонад", "лимонадом"),
    Action("water", "💧", "water glass fresh", ("=вода", "=воды", "=воду", "=водой", "водичк"), "drink", "воду", "водой"),
    Action("milkshake", "🥛", "milkshake", ("милкшейк", "молочный коктейль"), "drink", "молочный коктейль", "молочным коктейлем"),
    Action("bubble_tea", "🧋", "bubble tea", ("бабл", "bubble"), "drink", "бабл-ти", "бабл-ти"),

    # ЕДА
    Action("pizza", "🍕", "pizza delicious", ("пицц",), "food", "пиццу", "пиццей"),
    Action("burger", "🍔", "burger juicy", ("бургер", "гамбургер", "чизбургер"), "food", "бургер", "бургером"),
    Action("fries", "🍟", "fries french potato", ("=фри", "картошк", "картофел"), "food", "картошку фри", "картошкой фри"),
    Action("hotdog", "🌭", "hot dog", ("хотдог", "хот-дог"), "food", "хот-дог", "хот-догом"),
    Action("sushi", "🍣", "sushi japanese", ("суши", "роллы", "роллов"), "food", "суши", "суши"),
    Action("ramen", "🍜", "ramen noodle soup", ("рамен",), "food", "рамен", "раменом"),
    Action("pasta", "🍝", "pasta italian", ("=паста", "=пасту", "=пасты", "спагетти"), "food", "пасту", "пастой"),
    Action("steak", "🥩", "steak grilled", ("стейк",), "food", "стейк", "стейком"),
    Action("chicken", "🍗", "chicken fried", ("куриц", "курочк"), "food", "курицу", "курицей"),
    Action("meat", "🥩", "meat barbecue grilled", ("=мясо", "=мяса", "=мясом", "мяска", "шашлык"), "food", "мясо", "мясом"),
    Action("fish", "🐟", "fish grilled dish", ("=рыба", "=рыбу", "=рыбы", "=рыбой", "рыбк"), "food", "рыбу", "рыбой"),
    Action("shrimp", "🍤", "shrimp seafood", ("кревет",), "food", "креветки", "креветками"),
    Action("taco", "🌮", "tacos mexican food", ("=тако", "такос"), "food", "тако", "тако"),
    Action("burrito", "🌯", "burrito", ("буррит",), "food", "буррито", "буррито"),
    Action("sandwich", "🥪", "sandwich", ("сэндвич", "сендвич", "бутерброд"), "food", "сэндвич", "сэндвичем"),
    Action("salad", "🥗", "salad fresh", ("салат",), "food", "салат", "салатом"),
    Action("soup", "🍲", "soup homemade", ("=суп", "=супа", "=супу", "=супом", "супчик", "борщ"), "food", "суп", "супом"),
    Action("dumplings", "🥟", "dumplings", ("пельмен", "вареник"), "food", "пельмени", "пельменями"),
    Action("pancakes", "🥞", "pancakes breakfast sweet", ("блин", "блинчик", "оладь"), "food", "блины", "блинами"),
    Action("waffle", "🧇", "waffle dessert sweet", ("вафл",), "food", "вафлю", "вафлей"),

    # СЛАДКОЕ
    Action("cake", "🍰", "cake beautiful", ("торт", "тортик"), "food", "торт", "тортом"),
    Action("icecream", "🍦", "icecream dessert", ("морожен",), "food", "мороженое", "мороженым"),
    Action("chocolate", "🍫", "chocolate sweet", ("шоколад",), "food", "шоколад", "шоколадом"),
    Action("candy", "🍬", "candy sweets colorful", ("конфет",), "food", "конфеты", "конфетами"),
    Action("donut", "🍩", "donut glazed sweet", ("пончик", "донат"), "food", "пончик", "пончиком"),
    Action("cookie", "🍪", "cookies homemade sweet", ("печенье", "печеньк", "печеньем"), "food", "печенье", "печеньем"),
    Action("cupcake", "🧁", "cupcake", ("капкейк", "кекс"), "food", "капкейк", "капкейком"),
    Action("croissant", "🥐", "croissant bakery", ("круассан", "круасан"), "food", "круассан", "круассаном"),
    Action("banana", "🍌", "banana fruit yellow", ("банан",), "food", "банан", "бананом"),

    # ФРУКТЫ
    Action("strawberry", "🍓", "strawberries fresh", ("клубник",), "food", "клубнику", "клубникой"),
    Action("watermelon", "🍉", "watermelon slice", ("арбуз",), "food", "арбуз", "арбузом"),
    Action("apple", "🍎", "apple red", ("яблок", "яблоч"), "food", "яблоко", "яблоком"),
    Action("orange", "🍊", "orange fruit citrus", ("апельсин", "мандарин"), "food", "апельсин", "апельсином"),
    Action("grapes", "🍇", "grapes fruit", ("виноград",), "food", "виноград", "виноградом"),

    # ЦВЕТЫ — всегда букеты
    Action("rose", "🌹", "roses bouquet red", ("=розы", "=розу", "=роз", "розочк"), "flower", "букет роз", "букетом роз"),
    Action("tulips", "🌷", "tulips bouquet", ("тюльпан",), "flower", "букет тюльпанов", "букетом тюльпанов"),
    Action("sunflowers", "🌻", "sunflowers bouquet", ("подсолнух",), "flower", "букет подсолнухов", "букетом подсолнухов"),
    Action("flowers", "💐", "flowers bouquet beautiful", ("цветы", "цветочк", "цветок", "букет"), "flower", "букет цветов", "букетом цветов"),
    Action("orchid", "🌺", "orchid flowers bouquet", ("орхиде",), "flower", "букет орхидей", "букетом орхидей"),
    Action("lily", "🌸", "lilies bouquet", ("лилии", "лилию", "лилий"), "flower", "букет лилий", "букетом лилий"),

    # ПОДАРКИ
    Action("gift", "🎁", "gift present wrapped", ("подар", "презент"), "gift", "подарок", "подарком"),
    Action("teddy", "🧸", "teddy bear cute", ("мишк", "мишку", "плюшев"), "gift", "мишку", "мишкой"),
    Action("jewelry", "💎", "jewelry elegant gift", ("украшен", "ювелир", "колечк"), "gift", "украшение", "украшением"),

    # ДЕЙСТВИЯ (парные)
    Action("hug", "🤗", "warm friendly hug happy", ("обня", "обним", "обнимашк"), "pair"),
    Action("kiss", "😘", "happy couple kissing", ("поцелу", "поцело", "целу", "чмок"), "pair"),
    Action("highfive", "🙌", "friends high five happy", ("дай пять", "пятюн", "хайфайв", "=пять"), "pair"),
    Action("handshake", "🤝", "friendly handshake smiling", ("рукопожат", "пожми", "жму руку"), "pair"),
    Action("support", "🫶", "friends cheering each other up smiling", ("поддерж",), "pair"),
    Action("congratulations", "🎉", "friends congratulating celebration confetti", ("поздрав",), "pair"),
    Action("party", "🎉", "happy friends party celebration", ("вечерин", "тусов", "=праздник"), "pair"),
    Action("movie", "🎬", "friends watching movie popcorn", ("=кино", "фильм"), "pair"),
    Action("music", "🎵", "friends listening to music headphones", ("музык", "песн"), "pair"),
    Action("dance", "💃", "happy people dancing together", ("танц", "потанц"), "pair"),
]


ACTION_BY_KEY = {action.key: action for action in ACTIONS}


# ---------------------------------------------------------
# Параметры распознавания
# ---------------------------------------------------------

MAX_ACTION_WORDS = 3   # действие — короткая фраза, не предложение

# Сколько букв можно "дописать" после алиаса.
# У длинных основ хвост больше: "поцелу" -> "поцеловать".
ALIAS_TAIL_SHORT = 3
ALIAS_TAIL_LONG = 5
LONG_ALIAS_FROM = 6


def _allowed_tail(needle: str) -> int:
    return (
        ALIAS_TAIL_LONG
        if len(needle) >= LONG_ALIAS_FROM
        else ALIAS_TAIL_SHORT
    )

_WORD_RE = re.compile(r"[А-Яа-яЁёA-Za-z]+(?:-[А-Яа-яЁёA-Za-z]+)?")

# Слова, которые не мешают распознать действие.
STOP_WORDS = {
    "маруська", "маруся", "маруськa", "бот",
    "я", "ты", "он", "она", "мы", "вы", "они",
    "мне", "тебе", "ему", "ей", "нам", "вам", "им",
    "меня", "тебя", "его", "ее", "её", "их", "нас", "вас",
    "а", "и", "но", "да", "ну", "же", "бы", "ли", "вот", "тут", "там",
    "это", "эт", "так", "тоже", "ещё", "еще",
    "хочу", "хочет", "надо", "нужно", "давай", "дай", "держи", "лови",
    "плиз", "пожалуйста", "спасибо", "пж",
    "на", "с", "со", "за", "по", "в", "во", "к", "ко", "у", "от", "для",
}

# Явные ложные срабатывания.
BLACKLIST = {
    "супер", "суперски", "суперский", "супруг", "супруга", "супругой",
    "сокол", "соколов", "чайник", "чайники",
    "винил", "винить", "виноват", "виновата", "виновен",
    "джинсы", "джинса", "джинсов",
    "мясник", "мясная", "рыбак", "рыбалка", "рыбалку",
    "пастух", "пастор", "паства",
    "розетка", "розыгрыш", "розовый", "розовая",
    "цветной", "цветная", "цветение",
    "пятница", "пятьсот", "пятый", "пятая", "пятно",
    "опять", "повод", "поводу", "завод", "провод", "проводи",
    "высокий", "высоко", "громко", "ромашка", "мороз",
    "около", "молоко", "калории",
    "блин",  # чаще междометие, чем еда
}


def _normalize(word: str) -> str:
    return word.lower().replace("ё", "е")


def find_action(text: str | None) -> Action | None:
    """
    Возвращает Action, если сообщение является коротким действием.
    Во всех остальных случаях — None (и тогда сообщение уходит в AI).
    """
    if not text:
        return None

    stripped = text.strip()

    # Команды и длинные простыни — точно не действия.
    if stripped.startswith("/"):
        return None

    raw_words = [_normalize(w) for w in _WORD_RE.findall(stripped)]
    if not raw_words:
        return None

    if any(word in BLACKLIST for word in raw_words):
        return None

    words = [w for w in raw_words if w not in STOP_WORDS]
    if not words:
        return None

    if len(words) > MAX_ACTION_WORDS:
        return None

    phrase = " ".join(words)

    best: Action | None = None
    best_score = 0

    for action in ACTIONS:
        for alias in action.aliases:
            exact = alias.startswith("=")
            needle = _normalize(alias[1:] if exact else alias)

            score = len(needle)
            if score <= best_score:
                continue

            if " " in needle:
                matched = needle in phrase
            elif exact:
                matched = any(word == needle for word in words)
            else:
                tail = _allowed_tail(needle)
                matched = any(
                    word.startswith(needle)
                    and len(word) - len(needle) <= tail
                    for word in words
                )

            if matched:
                best = action
                best_score = score

    return best
