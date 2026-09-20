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
    Action("beer", "🍺", "beer drink", ("пив", "beer"), "drink", "пиво", "пивом"),
    Action("coffee", "☕", "coffee cup", ("кофе",), "drink", "кофе", "кофе"),
    Action("tea", "🍵", "tea cup", ("чай", "чаем"), "drink", "чай", "чаем"),
    Action("wine", "🍷", "wine glass", ("вин",), "drink", "вино", "вином"),
    Action("champagne", "🥂", "champagne toast", ("шампан",), "drink", "шампанское", "шампанским"),
    Action("whiskey", "🥃", "whiskey glass", ("виски",), "drink", "виски", "виски"),
    Action("cognac", "🥃", "cognac glass", ("коньяк",), "drink", "коньяк", "коньяком"),
    Action("vodka", "🍸", "vodka drink", ("водк",), "drink", "водку", "водкой"),
    Action("moonshine", "🥃", "moonshine homemade alcohol", ("брага", "самогон"), "drink", "брагу", "брагой"),
    Action("rum", "🥃", "rum drink", ("ром",), "drink", "ром", "ромом"),
    Action("gin", "🍸", "gin tonic", ("джин",), "drink", "джин", "джином"),
    Action("tequila", "🍹", "tequila drink", ("текил",), "drink", "текилу", "текилой"),
    Action("cocktail", "🍹", "cocktail drink", ("коктейл",), "drink", "коктейль", "коктейлем"),
    Action("martini", "🍸", "martini cocktail", ("мартини",), "drink", "мартини", "мартини"),
    Action("juice", "🧃", "fresh juice", ("сок",), "drink", "сок", "соком"),
    Action("cola", "🥤", "cola drink", ("кола", "колой"), "drink", "колу", "колой"),
    Action("lemonade", "🍋", "lemonade drink", ("лимонад",), "drink", "лимонад", "лимонадом"),
    Action("water", "💧", "glass of water", ("вод",), "drink", "воду", "водой"),
    Action("milkshake", "🥛", "milkshake", ("молочн", "милкшейк"), "drink", "молочный коктейль", "молочным коктейлем"),
    Action("bubble_tea", "🧋", "bubble tea", ("бабл", "bubble"), "drink", "бабл-ти", "бабл-ти"),

    # ЕДА
    Action("pizza", "🍕", "pizza", ("пицц",), "food", "пиццу", "пиццей"),
    Action("burger", "🍔", "burger", ("бургер",), "food", "бургер", "бургером"),
    Action("fries", "🍟", "french fries", ("фри", "картошк"), "food", "картошку фри", "картошкой фри"),
    Action("hotdog", "🌭", "hot dog", ("хотдог", "хот-дог"), "food", "хот-дог", "хот-догом"),
    Action("sushi", "🍣", "sushi", ("суши",), "food", "суши", "суши"),
    Action("ramen", "🍜", "ramen noodles", ("рамен",), "food", "рамен", "раменом"),
    Action("pasta", "🍝", "pasta", ("паст",), "food", "пасту", "пастой"),
    Action("steak", "🥩", "steak", ("стейк",), "food", "стейк", "стейком"),
    Action("chicken", "🍗", "fried chicken", ("куриц",), "food", "курицу", "курицей"),
    Action("meat", "🥩", "grilled meat", ("мяс",), "food", "мясо", "мясом"),
    Action("fish", "🐟", "grilled fish", ("рыб",), "food", "рыбу", "рыбой"),
    Action("shrimp", "🍤", "shrimp", ("кревет",), "food", "креветки", "креветками"),
    Action("taco", "🌮", "tacos", ("тако",), "food", "тако", "тако"),
    Action("burrito", "🌯", "burrito", ("буррит",), "food", "буррито", "буррито"),
    Action("sandwich", "🥪", "sandwich", ("сэндвич",), "food", "сэндвич", "сэндвичем"),
    Action("salad", "🥗", "fresh salad", ("салат",), "food", "салат", "салатом"),
    Action("soup", "🍲", "soup", ("суп",), "food", "суп", "супом"),
    Action("dumplings", "🥟", "dumplings", ("пельмен",), "food", "пельмени", "пельменями"),
    Action("pancakes", "🥞", "pancakes", ("блин",), "food", "блины", "блинами"),
    Action("waffle", "🧇", "waffle", ("вафл",), "food", "вафлю", "вафлей"),

    # СЛАДКОЕ
    Action("cake", "🍰", "cake", ("торт",), "food", "торт", "тортом"),
    Action("icecream", "🍦", "ice cream", ("морожен",), "food", "мороженое", "мороженым"),
    Action("chocolate", "🍫", "chocolate", ("шоколад",), "food", "шоколад", "шоколадом"),
    Action("candy", "🍬", "candy sweets", ("конфет",), "food", "конфеты", "конфетами"),
    Action("donut", "🍩", "donut", ("пончик",), "food", "пончик", "пончиком"),
    Action("cookie", "🍪", "cookies", ("печень",), "food", "печенье", "печеньем"),
    Action("cupcake", "🧁", "cupcake", ("капкейк",), "food", "капкейк", "капкейком"),
    Action("croissant", "🥐", "croissant", ("круассан",), "food", "круассан", "круассаном"),
    Action("banana", "🍌", "banana", ("банан",), "food", "банан", "бананом"),

    # ФРУКТЫ
    Action("strawberry", "🍓", "strawberries", ("клубник",), "food", "клубнику", "клубникой"),
    Action("watermelon", "🍉", "watermelon", ("арбуз",), "food", "арбуз", "арбузом"),
    Action("apple", "🍎", "red apple", ("яблок",), "food", "яблоко", "яблоком"),
    Action("orange", "🍊", "orange fruit", ("апельсин",), "food", "апельсин", "апельсином"),
    Action("grapes", "🍇", "grapes", ("виноград",), "food", "виноград", "виноградом"),

    # ЦВЕТЫ — всегда букеты
    Action("rose", "🌹", "red roses bouquet", ("роз",), "flower", "букет роз", "букетом роз"),
    Action("tulips", "🌷", "tulips bouquet", ("тюльпан",), "flower", "букет тюльпанов", "букетом тюльпанов"),
    Action("sunflowers", "🌻", "sunflowers bouquet", ("подсолнух",), "flower", "букет подсолнухов", "букетом подсолнухов"),
    Action("flowers", "💐", "beautiful mixed flower bouquet", ("цвет", "букет"), "flower", "букет цветов", "букетом цветов"),
    Action("orchid", "🌺", "orchid bouquet", ("орхиде",), "flower", "букет орхидей", "букетом орхидей"),
    Action("lily", "🌸", "lily bouquet", ("лили",), "flower", "букет лилий", "букетом лилий"),

    # ПОДАРКИ
    Action("gift", "🎁", "wrapped gift", ("подар",), "gift", "подарок", "подарком"),
    Action("teddy", "🧸", "cute teddy bear gift", ("мишк",), "gift", "мишку", "мишкой"),
    Action("jewelry", "💎", "elegant jewelry gift", ("украшен", "ювелир"), "gift", "украшение", "украшением"),

    # ДЕЙСТВИЯ
    Action("hug", "🤗", "people hugging", ("обня", "обним"), "pair"),
    Action("kiss", "😘", "people kissing", ("поцелу", "целу"), "pair"),
    Action("highfive", "🙌", "people high five", ("дай пять", "хайфайв", "пять"), "pair"),
    Action("handshake", "🤝", "people handshake", ("рукопожат", "пожми"), "pair"),
    Action("support", "🫶", "people supporting each other", ("поддерж",), "pair"),
    Action("congratulations", "🎉", "people celebrating congratulations", ("поздрав",), "pair"),
    Action("party", "🎉", "people at a party", ("вечерин", "праздник"), "pair"),
    Action("movie", "🎬", "people watching movie together", ("кино", "фильм"), "pair"),
    Action("music", "🎵", "people listening to music together", ("музык", "песн"), "pair"),
    Action("dance", "💃", "people dancing together", ("танц",), "pair"),
]


ACTION_BY_KEY = {action.key: action for action in ACTIONS}


def find_action(text: str) -> Action | None:
    normalized = " ".join(text.lower().strip().split())
    for action in ACTIONS:
        for alias in sorted(action.aliases, key=len, reverse=True):
            if alias in normalized:
                return action
    return None
