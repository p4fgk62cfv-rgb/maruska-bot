from dataclasses import dataclass


@dataclass(frozen=True)
class Action:
    key: str
    emoji: str
    search: str
    aliases: tuple[str, ...]
    item_acc: str
    item_instr: str


ACTIONS = [

    # =====================================================
    # НАПИТКИ
    # =====================================================

    Action(
        "beer",
        "🍺",
        "beer drink",
        ("пив", "beer"),
        "пиво",
        "пивом",
    ),

    Action(
        "coffee",
        "☕",
        "coffee cup",
        ("кофе",),
        "кофе",
        "кофе",
    ),

    Action(
        "tea",
        "🍵",
        "tea cup",
        ("чай", "чаем"),
        "чай",
        "чаем",
    ),

    Action(
        "wine",
        "🍷",
        "wine glass",
        ("вин",),
        "вино",
        "вином",
    ),

    Action(
        "champagne",
        "🥂",
        "champagne toast",
        ("шампан",),
        "шампанское",
        "шампанским",
    ),

    Action(
        "whiskey",
        "🥃",
        "whiskey glass",
        ("виски",),
        "виски",
        "виски",
    ),

    Action(
        "cognac",
        "🥃",
        "cognac glass",
        ("коньяк",),
        "коньяк",
        "коньяком",
    ),

    Action(
        "vodka",
        "🍸",
        "vodka drink",
        ("водк",),
        "водку",
        "водкой",
    ),

    Action(
        "rum",
        "🥃",
        "rum drink",
        ("ром",),
        "ром",
        "ромом",
    ),

    Action(
        "gin",
        "🍸",
        "gin tonic",
        ("джин",),
        "джин",
        "джином",
    ),

    Action(
        "tequila",
        "🍹",
        "tequila drink",
        ("текил",),
        "текилу",
        "текилой",
    ),

    Action(
        "cocktail",
        "🍹",
        "cocktail drink",
        ("коктейл",),
        "коктейль",
        "коктейлем",
    ),

    Action(
        "martini",
        "🍸",
        "martini cocktail",
        ("мартини",),
        "мартини",
        "мартини",
    ),

    Action(
        "juice",
        "🧃",
        "fresh juice",
        ("сок",),
        "сок",
        "соком",
    ),

    Action(
        "cola",
        "🥤",
        "cola drink",
        ("кола", "колой"),
        "колу",
        "колой",
    ),

    Action(
        "lemonade",
        "🍋",
        "lemonade drink",
        ("лимонад",),
        "лимонад",
        "лимонадом",
    ),

    Action(
        "water",
        "💧",
        "glass of water",
        ("вод",),
        "воды",
        "водой",
    ),

    Action(
        "milkshake",
        "🥛",
        "milkshake",
        ("молочн", "милкшейк"),
        "молочный коктейль",
        "молочным коктейлем",
    ),

    Action(
        "bubble_tea",
        "🧋",
        "bubble tea",
        ("бабл", "bubble"),
        "бабл-ти",
        "бабл-ти",
    ),


    # =====================================================
    # ЕДА
    # =====================================================

    Action(
        "pizza",
        "🍕",
        "pizza",
        ("пицц",),
        "пиццу",
        "пиццей",
    ),

    Action(
        "burger",
        "🍔",
        "burger",
        ("бургер",),
        "бургер",
        "бургером",
    ),

    Action(
        "fries",
        "🍟",
        "french fries",
        ("фри", "картошк"),
        "картошку фри",
        "картошкой фри",
    ),

    Action(
        "hotdog",
        "🌭",
        "hot dog",
        ("хотдог", "хот-дог"),
        "хот-дог",
        "хот-догом",
    ),

    Action(
        "sushi",
        "🍣",
        "sushi",
        ("суши",),
        "суши",
        "суши",
    ),

    Action(
        "ramen",
        "🍜",
        "ramen noodles",
        ("рамен",),
        "рамен",
        "раменом",
    ),

    Action(
        "pasta",
        "🍝",
        "pasta",
        ("паст",),
        "пасту",
        "пастой",
    ),

    Action(
        "steak",
        "🥩",
        "steak",
        ("стейк",),
        "стейк",
        "стейком",
    ),

    Action(
        "chicken",
        "🍗",
        "fried chicken",
        ("куриц",),
        "курицу",
        "курицей",
    ),

    Action(
        "meat",
        "🥩",
        "grilled meat",
        ("мяс",),
        "мясо",
        "мясом",
    ),

    Action(
        "fish",
        "🐟",
        "grilled fish",
        ("рыб",),
        "рыбу",
        "рыбой",
    ),

    Action(
        "shrimp",
        "🍤",
        "shrimp",
        ("кревет",),
        "креветки",
        "креветками",
    ),

    Action(
        "taco",
        "🌮",
        "tacos",
        ("тако",),
        "тако",
        "тако",
    ),

    Action(
        "burrito",
        "🌯",
        "burrito",
        ("буррит",),
        "буррито",
        "буррито",
    ),

    Action(
        "sandwich",
        "🥪",
        "sandwich",
        ("сэндвич",),
        "сэндвич",
        "сэндвичем",
    ),

    Action(
        "salad",
        "🥗",
        "fresh salad",
        ("салат",),
        "салат",
        "салатом",
    ),

    Action(
        "soup",
        "🍲",
        "soup",
        ("суп",),
        "суп",
        "супом",
    ),

    Action(
        "dumplings",
        "🥟",
        "dumplings",
        ("пельмен",),
        "пельмени",
        "пельменями",
    ),

    Action(
        "pancakes",
        "🥞",
        "pancakes",
        ("блин",),
        "блины",
        "блинами",
    ),

    Action(
        "waffle",
        "🧇",
        "waffle",
        ("вафл",),
        "вафлю",
        "вафлей",
    ),


    # =====================================================
    # СЛАДКОЕ
    # =====================================================

    Action(
        "cake",
        "🍰",
        "cake",
        ("торт",),
        "торт",
        "тортом",
    ),

    Action(
        "icecream",
        "🍦",
        "ice cream",
        ("морожен",),
        "мороженое",
        "мороженым",
    ),

    Action(
        "chocolate",
        "🍫",
        "chocolate",
        ("шоколад",),
        "шоколад",
        "шоколадом",
    ),

    Action(
        "candy",
        "🍬",
        "candy sweets",
        ("конфет",),
        "конфеты",
        "конфетами",
    ),

    Action(
        "donut",
        "🍩",
        "donut",
        ("пончик",),
        "пончик",
        "пончиком",
    ),

    Action(
        "cookie",
        "🍪",
        "cookies",
        ("печень",),
        "печенье",
        "печеньем",
    ),

    Action(
        "cupcake",
        "🧁",
        "cupcake",
        ("капкейк",),
        "капкейк",
        "капкейком",
    ),

    Action(
        "croissant",
        "🥐",
        "croissant",
        ("круассан",),
        "круассан",
        "круассаном",
    ),


    # =====================================================
    # ФРУКТЫ
    # =====================================================

    Action(
        "strawberry",
        "🍓",
        "strawberries",
        ("клубник",),
        "клубнику",
        "клубникой",
    ),

    Action(
        "watermelon",
        "🍉",
        "watermelon",
        ("арбуз",),
        "арбуз",
        "арбузом",
    ),

    Action(
        "banana",
        "🍌",
        "banana",
        ("банан",),
        "банан",
        "бананом",
    ),

    Action(
        "apple",
        "🍎",
        "red apple",
        ("яблок",),
        "яблоко",
        "яблоком",
    ),

    Action(
        "orange",
        "🍊",
        "orange fruit",
        ("апельсин",),
        "апельсин",
        "апельсином",
    ),

    Action(
        "grapes",
        "🍇",
        "grapes",
        ("виноград",),
        "виноград",
        "виноградом",
    ),


    # =====================================================
    # ЦВЕТЫ
    # =====================================================

    Action(
        "rose",
        "🌹",
        "red roses bouquet",
        ("роз",),
        "розу",
        "розой",
    ),

    Action(
        "tulips",
        "🌷",
        "tulips bouquet",
        ("тюльпан",),
        "тюльпаны",
        "тюльпанами",
    ),

    Action(
        "sunflowers",
        "🌻",
        "sunflowers bouquet",
        ("подсолнух",),
        "подсолнухи",
        "подсолнухами",
    ),

    Action(
        "flowers",
        "💐",
        "beautiful flower bouquet",
        ("цвет", "букет"),
        "цветы",
        "цветами",
    ),

    Action(
        "orchid",
        "🌺",
        "orchid flowers",
        ("орхиде",),
        "орхидею",
        "орхидеей",
    ),

    Action(
        "lily",
        "🌸",
        "lily flowers",
        ("лили",),
        "лилию",
        "лилией",
    ),


    # =====================================================
    # ПОДАРКИ
    # =====================================================

    Action(
        "gift",
        "🎁",
        "wrapped gift",
        ("подар",),
        "подарок",
        "подарком",
    ),

    Action(
        "teddy",
        "🧸",
        "cute teddy bear gift",
        ("мишк",),
        "мишку",
        "мишкой",
    ),

    Action(
        "jewelry",
        "💎",
        "elegant jewelry gift",
        ("украшен", "ювелир"),
        "украшение",
        "украшением",
    ),


    # =====================================================
    # ОБЩЕНИЕ И ДЕЙСТВИЯ
    # =====================================================

    Action(
        "hug",
        "🤗",
        "friends hugging",
        ("обня", "обним"),
        "объятие",
        "объятиями",
    ),

    Action(
        "kiss",
        "😘",
        "friendly kiss",
        ("поцелу", "целу"),
        "поцелуй",
        "поцелуем",
    ),

    Action(
        "highfive",
        "🙌",
        "friends high five",
        ("пять", "дай пять", "хайфайв"),
        "пять",
        "пятью",
    ),

    Action(
        "handshake",
        "🤝",
        "friends handshake",
        ("рукопожат", "пожми"),
        "руку",
        "рукопожатием",
    ),

    Action(
        "support",
        "🫶",
        "friends supporting each other",
        ("поддерж",),
        "поддержку",
        "поддержкой",
    ),

    Action(
        "congratulations",
        "🎉",
        "celebration congratulations",
        ("поздрав",),
        "поздравление",
        "поздравлением",
    ),

    Action(
        "party",
        "🎉",
        "party celebration",
        ("вечерин", "праздник"),
        "вечеринку",
        "вечеринкой",
    ),

    Action(
        "movie",
        "🎬",
        "friends watching movie",
        ("кино", "фильм"),
        "фильм",
        "фильмом",
    ),

    Action(
        "music",
        "🎵",
        "friends listening to music",
        ("музык", "песн"),
        "музыку",
        "музыкой",
    ),

    Action(
        "dance",
        "💃",
        "friends dancing",
        ("танц",),
        "танец",
        "танцем",
    ),
]


ACTION_BY_KEY = {
    action.key: action
    for action in ACTIONS
}


def find_action(text: str) -> Action | None:

    normalized = text.lower().strip()

    for action in ACTIONS:

        for alias in action.aliases:

            if alias in normalized:
                return action

    return None
