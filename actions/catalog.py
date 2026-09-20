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
    Action("beer", "🍺", "beer glass drink photo", ("пив", "beer"), "drink", "пиво", "пивом"),
    Action("coffee", "☕", "coffee cup drink photo", ("кофе",), "drink", "кофе", "кофе"),
    Action("tea", "🍵", "tea cup drink photo", ("чай", "чаем"), "drink", "чай", "чаем"),
    Action("wine", "🍷", "wine glass drink photo", ("вин",), "drink", "вино", "вином"),
    Action("champagne", "🥂", "champagne glasses toast photo", ("шампан",), "drink", "шампанское", "шампанским"),
    Action("whiskey", "🥃", "whiskey glass drink photo", ("виски",), "drink", "виски", "виски"),
    Action("cognac", "🥃", "cognac glass drink photo", ("коньяк",), "drink", "коньяк", "коньяком"),
    Action("vodka", "🍸", "vodka glass drink photo", ("водк",), "drink", "водку", "водкой"),
    Action("moonshine", "🥃", "homemade moonshine alcohol drink photo", ("брага", "самогон"), "drink", "брагу", "брагой"),
    Action("rum", "🥃", "rum glass drink photo", ("ром",), "drink", "ром", "ромом"),
    Action("gin", "🍸", "gin tonic glass drink photo", ("джин",), "drink", "джин", "джином"),
    Action("tequila", "🍹", "tequila shot drink photo", ("текил",), "drink", "текилу", "текилой"),
    Action("cocktail", "🍹", "cocktail glass drink photo", ("коктейл",), "drink", "коктейль", "коктейлем"),
    Action("martini", "🍸", "martini cocktail glass photo", ("мартини",), "drink", "мартини", "мартини"),
    Action("juice", "🧃", "glass of fruit juice photo", ("сок",), "drink", "сок", "соком"),
    Action("cola", "🥤", "cola drink glass photo", ("кола", "колой"), "drink", "колу", "колой"),
    Action("lemonade", "🍋", "lemonade glass drink photo", ("лимонад",), "drink", "лимонад", "лимонадом"),
    Action("water", "💧", "glass of water drink photo", ("вод",), "drink", "воду", "водой"),
    Action("milkshake", "🥛", "milkshake glass drink photo", ("молочн", "милкшейк"), "drink", "молочный коктейль", "молочным коктейлем"),
    Action("bubble_tea", "🧋", "bubble tea cup drink photo", ("бабл", "bubble"), "drink", "бабл-ти", "бабл-ти"),

    # ЕДА
    Action("pizza", "🍕", "pizza food photo", ("пицц",), "food", "пиццу", "пиццей"),
    Action("burger", "🍔", "hamburger burger food photo", ("бургер",), "food", "бургер", "бургером"),
    Action("fries", "🍟", "french fries food photo", ("фри", "картошк"), "food", "картошку фри", "картошкой фри"),
    Action("hotdog", "🌭", "hot dog food photo", ("хотдог", "хот-дог"), "food", "хот-дог", "хот-догом"),
    Action("sushi", "🍣", "sushi food photo", ("суши",), "food", "суши", "суши"),
    Action("ramen", "🍜", "ramen noodles food photo", ("рамен",), "food", "рамен", "раменом"),
    Action("pasta", "🍝", "pasta food photo", ("паст",), "food", "пасту", "пастой"),
    Action("steak", "🥩", "steak food photo", ("стейк",), "food", "стейк", "стейком"),
    Action("chicken", "🍗", "chicken food dish photo", ("куриц",), "food", "курицу", "курицей"),
    Action("meat", "🥩", "cooked meat food photo", ("мяс",), "food", "мясо", "мясом"),
    Action("fish", "🐟", "cooked fish food photo", ("рыб",), "food", "рыбу", "рыбой"),
    Action("shrimp", "🍤", "cooked shrimp food photo", ("кревет",), "food", "креветки", "креветками"),
    Action("taco", "🌮", "taco food photo", ("тако",), "food", "тако", "тако"),
    Action("burrito", "🌯", "burrito food photo", ("буррит",), "food", "буррито", "буррито"),
    Action("sandwich", "🥪", "sandwich food photo", ("сэндвич",), "food", "сэндвич", "сэндвичем"),
    Action("salad", "🥗", "fresh salad food photo", ("салат",), "food", "салат", "салатом"),
    Action("soup", "🍲", "soup food bowl photo", ("суп",), "food", "суп", "супом"),
    Action("dumplings", "🥟", "dumplings food photo", ("пельмен",), "food", "пельмени", "пельменями"),
    Action("pancakes", "🥞", "pancakes food photo", ("блин",), "food", "блины", "блинами"),
    Action("waffle", "🧇", "waffle food photo", ("вафл",), "food", "вафлю", "вафлей"),
    Action("cake", "🍰", "cake dessert food photo", ("торт",), "food", "торт", "тортом"),
    Action("icecream", "🍦", "ice cream dessert photo", ("морожен",), "food", "мороженое", "мороженым"),
    Action("chocolate", "🍫", "chocolate bar dessert photo", ("шоколад",), "food", "шоколад", "шоколадом"),
    Action("candy", "🍬", "candy sweets dessert photo", ("конфет",), "food", "конфеты", "конфетами"),
    Action("donut", "🍩", "donut dessert food photo", ("пончик",), "food", "пончик", "пончиком"),
    Action("cookie", "🍪", "cookies dessert food photo", ("печень",), "food", "печенье", "печеньем"),
    Action("cupcake", "🧁", "cupcake dessert food photo", ("капкейк",), "food", "капкейк", "капкейком"),
    Action("croissant", "🥐", "croissant pastry food photo", ("круассан",), "food", "круассан", "круассаном"),
    Action("banana", "🍌", "fresh whole banana fruit food photo", ("банан",), "food", "банан", "бананом"),
    Action("strawberry", "🍓", "fresh strawberries fruit food photo", ("клубник",), "food", "клубнику", "клубникой"),
    Action("watermelon", "🍉", "fresh watermelon fruit food photo", ("арбуз",), "food", "арбуз", "арбузом"),
    Action("apple", "🍎", "fresh red apple fruit food photo", ("яблок",), "food", "яблоко", "яблоком"),
    Action("orange", "🍊", "fresh orange fruit food photo", ("апельсин",), "food", "апельсин", "апельсином"),
    Action("grapes", "🍇", "fresh grapes fruit food photo", ("виноград",), "food", "виноград", "виноградом"),

    # ЦВЕТЫ — букеты
    Action("rose", "🌹", "bouquet of red roses flowers photo", ("роз",), "flower", "букет роз", "букетом роз"),
    Action("tulips", "🌷", "bouquet of tulips flowers photo", ("тюльпан",), "flower", "букет тюльпанов", "букетом тюльпанов"),
    Action("sunflowers", "🌻", "bouquet of sunflowers flowers photo", ("подсолнух",), "flower", "букет подсолнухов", "букетом подсолнухов"),
    Action("flowers", "💐", "beautiful mixed flower bouquet photo", ("цвет", "букет"), "flower", "букет цветов", "букетом цветов"),
    Action("orchid", "🌺", "bouquet of orchids flowers photo", ("орхиде",), "flower", "букет орхидей", "букетом орхидей"),
    Action("lily", "🌸", "bouquet of lilies flowers photo", ("лили",), "flower", "букет лилий", "букетом лилий"),

    # ПОДАРКИ
    Action("gift", "🎁", "wrapped gift box present photo", ("подар",), "gift", "подарок", "подарком"),
    Action("teddy", "🧸", "cute teddy bear gift photo", ("мишк",), "gift", "мишку", "мишкой"),
    Action("jewelry", "💎", "elegant jewelry gift photo", ("украшен", "ювелир"), "gift", "украшение", "украшением"),

    # ПАРНЫЕ ДЕЙСТВИЯ
    Action("hug", "🤗", "people hugging together photo", ("обня", "обним"), "pair"),
    Action("kiss", "😘", "people kissing together photo", ("поцелу", "целу"), "pair"),
    Action("highfive", "🙌", "people high five together photo", ("дай пять", "хайфайв", "пять"), "pair"),
    Action("handshake", "🤝", "people handshake together photo", ("рукопожат", "пожми"), "pair"),
    Action("support", "🫶", "people supporting each other photo", ("поддерж"), "pair"),
    Action("congratulations", "🎉", "people celebrating congratulations together photo", ("поздрав"), "pair"),
    Action("party", "🎉", "people at a party together photo", ("вечерин", "праздник"), "pair"),
    Action("movie", "🎬", "people watching movie together photo", ("кино", "фильм"), "pair"),
    Action("music", "🎵", "people listening to music together photo", ("музык", "песн"), "pair"),
    Action("dance", "💃", "people dancing together photo", ("танц",), "pair"),
]

ACTION_BY_KEY = {action.key: action for action in ACTIONS}


def find_action(text: str) -> Action | None:
    normalized = " ".join(text.lower().strip().split())
    # Сначала более специфичные фразы, затем остальные.
    for action in sorted(ACTIONS, key=lambda a: max(map(len, a.aliases)), reverse=True):
        for alias in sorted(action.aliases, key=len, reverse=True):
            if alias in normalized:
                return action
    return None
