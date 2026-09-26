"""
Подбор картинок для действий.

Коллекция хранится отдельно для каждого источника и каждой
комбинации пола: "pixabay/hug:male_female".

Пока в коллекции есть неиспользованные картинки — берём оттуда.
Кончились — дозапрашиваем следующую страницу у источника.
Источник больше ничего не отдаёт — сбрасываем цикл и идём по кругу.
"""

import hashlib
import logging
import random
from dataclasses import dataclass

from actions.catalog import ACTIONS, Action, excluded_tags, required_tags
from actions.providers import (
    available_providers,
    download_photo,
    search_photos,
)
from database.repository import (
    count_cached_images,
    get_cached_action_image,
    known_photo_ids,
    reset_cached_images,
)


PAGES_PER_FILL = 2


# ---------------------------------------------------------
# Поисковые запросы для парных действий.
#
# Намеренно тёплые и позитивные: нейтральное
# "people supporting each other" сток отдаёт как
# депрессивную документалку.
#
# Короткие: Pixabay ищет по всем словам сразу, длинная фраза
# легко даёт ноль результатов.
# ---------------------------------------------------------

# ---------------------------------------------------------
# Внутренние Pixabay-профили для ВСЕХ Actions.
#
# Пользовательский текст сюда никогда не попадает. Сначала handler
# определяет Action (например, «Мара мяу» -> cat), затем этот Action
# получает свой англоязычный query и жёсткие требования к тегам.
# ---------------------------------------------------------

PAIR_SEARCHES = {
    "male_female": {
        "hug": "happy couple hugging",
        "kiss": "romantic couple kissing",
        "carry": "man carrying woman piggyback",
        "pat": "person gently patting head",
        "tickle": "friends tickling laughing",
        "wake": "person waking friend morning",
        "lull": "parent soothing sleeping person",
        "cover": "person covering friend with blanket",
        "photo": "friends taking portrait photo",
        "wink": "playful couple smiling",
        "sing": "couple singing microphone",
        "praise": "friends applauding praising",
        "scold": "person playfully scolding friend",
        "walk_home": "couple walking together evening street",
        "highfive": "man woman high five",
        "handshake": "man woman handshake smiling",
        "support": "friends supporting each other",
        "congratulations": "couple celebrating congratulations confetti",
        "party": "couple party celebration",
        "movie": "couple movie popcorn cinema",
        "music": "couple listening music headphones",
        "dance": "couple dancing happy",
        "banya": "couple sauna spa",
        "fishing": "couple fishing lake",
        "gym": "couple workout gym",
        "game": "friends gaming together",
        "selfie": "couple selfie smiling",
        "sea": "couple beach sea vacation",
        "walk": "couple walking park",
        "coffee_break": "friends coffee break talking",
    },
    "male_male": {
        "hug": "happy friends men hugging",
        "kiss": "men kissing couple",
        "carry": "man carrying friend piggyback",
        "pat": "man gently patting friend head",
        "tickle": "friends men tickling laughing",
        "wake": "man waking friend morning",
        "lull": "man soothing sleeping friend",
        "cover": "man covering friend blanket",
        "photo": "male friends taking portrait photo",
        "wink": "male friends playful smiling",
        "sing": "men singing microphone",
        "praise": "male friends applauding",
        "scold": "man playfully scolding friend",
        "walk_home": "male friends walking evening street",
        "highfive": "men high five",
        "handshake": "men handshake smiling",
        "support": "male friends supporting each other",
        "congratulations": "male friends celebration confetti",
        "party": "male friends party celebration",
        "movie": "male friends movie popcorn",
        "music": "male friends listening music",
        "dance": "men dancing happy",
        "banya": "men sauna spa",
        "fishing": "men fishing lake",
        "gym": "men workout gym",
        "game": "male friends gaming together",
        "selfie": "male friends selfie smiling",
        "sea": "male friends beach vacation",
        "walk": "male friends walking park",
        "coffee_break": "male friends coffee break talking",
    },
    "female_female": {
        "hug": "happy friends women hugging",
        "kiss": "women kissing couple",
        "carry": "woman carrying friend piggyback",
        "pat": "woman gently patting friend head",
        "tickle": "women friends tickling laughing",
        "wake": "woman waking friend morning",
        "lull": "woman soothing sleeping friend",
        "cover": "woman covering friend blanket",
        "photo": "female friends taking portrait photo",
        "wink": "female friends playful smiling",
        "sing": "women singing microphone",
        "praise": "female friends applauding",
        "scold": "woman playfully scolding friend",
        "walk_home": "female friends walking evening street",
        "highfive": "women high five",
        "handshake": "women handshake smiling",
        "support": "female friends supporting each other",
        "congratulations": "female friends celebration confetti",
        "party": "female friends party celebration",
        "movie": "female friends movie popcorn",
        "music": "female friends listening music",
        "dance": "women dancing happy",
        "banya": "women sauna spa",
        "fishing": "women fishing lake",
        "gym": "women workout gym",
        "game": "female friends gaming together",
        "selfie": "female friends selfie smiling",
        "sea": "female friends beach vacation",
        "walk": "female friends walking park",
        "coffee_break": "female friends coffee break talking",
    },
    "neutral": {
        "hug": "happy friends hugging",
        "kiss": "romantic couple kissing",
        "carry": "person carrying friend piggyback",
        "pat": "person gently patting friend head",
        "tickle": "friends tickling laughing",
        "wake": "person waking friend morning",
        "lull": "person soothing sleeping friend",
        "cover": "person covering friend blanket",
        "photo": "friends taking portrait photo",
        "wink": "friends playful smiling",
        "sing": "people singing microphone",
        "praise": "friends applauding praising",
        "scold": "person playfully scolding friend",
        "walk_home": "friends walking together evening street",
        "highfive": "friends high five",
        "handshake": "people handshake smiling",
        "support": "friends supporting each other",
        "congratulations": "friends celebration confetti",
        "party": "friends party celebration",
        "movie": "friends movie popcorn cinema",
        "music": "friends listening music headphones",
        "dance": "people dancing happy",
        "banya": "friends sauna spa",
        "fishing": "friends fishing lake",
        "gym": "friends workout gym",
        "game": "friends gaming together",
        "selfie": "friends selfie smiling",
        "sea": "friends beach sea vacation",
        "walk": "friends walking park",
        "coffee_break": "friends coffee break talking",
    },
}

# Узкие запросы для предметных Actions. Все 205 Actions получают профиль:
# если ключ здесь не переопределён, используется action.search + action.tags
# как обязательная смысловая группа.
PIXABAY_QUERY_OVERRIDES = {
    "beer": "beer glass pub",
    "wine": "wine glass bottle",
    "champagne": "champagne toast celebration",
    "whiskey": "whiskey glass bourbon",
    "cognac": "cognac brandy glass",
    "vodka": "vodka shot glass",
    "moonshine": "moonshine homemade alcohol",
    "rum": "rum glass bottle",
    "gin": "gin tonic glass",
    "tequila": "tequila shot lime",
    "cocktail": "cocktail glass bar",
    "martini": "martini cocktail glass",
    "mojito": "mojito cocktail mint",
    "aperol": "aperol spritz orange",
    "sake": "sake japanese drink",
    "cider": "apple cider drink",
    "mulled_wine": "mulled wine spices",
    "mead": "mead honey drink",
    "tincture": "herbal tincture bottle",
    "liqueur": "liqueur bottle glass",
    "coffee": "coffee cup cappuccino latte",
    "tea": "tea cup teapot",
    "cocoa": "hot cocoa mug",
    "matcha": "matcha green tea latte",
    "juice": "fresh fruit juice glass",
    "smoothie": "fruit smoothie glass",
    "cola": "cola soda glass",
    "lemonade": "fresh lemonade glass",
    "energy": "energy drink can",
    "water": "water glass bottle",
    "milkshake": "milkshake glass",
    "bubble_tea": "bubble tea boba cup",
    "kvass": "kvass drink bottle",
    "compote": "berry compote drink glass",
    "milk": "milk glass bottle",
    "kefir": "kefir yogurt drink glass",
    "pizza": "pizza whole slice",
    "burger": "burger hamburger",
    "fries": "french fries potato",
    "hotdog": "hot dog sausage",
    "shawarma": "shawarma kebab wrap",
    "sushi": "sushi japanese food",
    "ramen": "ramen noodle soup bowl",
    "pasta": "pasta spaghetti italian food",
    "lasagna": "lasagna italian dish",
    "steak": "grilled steak beef",
    "chicken": "fried chicken roasted chicken",
    "meat": "grilled meat barbecue",
    "cutlet": "meat cutlet homemade",
    "sausages": "grilled sausages",
    "bacon": "fried bacon breakfast",
    "eggs": "fried eggs omelette breakfast",
    "fish": "grilled fish salmon dish",
    "herring": "herring fish food",
    "caviar": "caviar delicacy",
    "shrimp": "shrimp seafood dish",
    "taco": "tacos mexican food",
    "burrito": "burrito mexican food",
    "sandwich": "sandwich toast bread",
    "salad": "fresh salad bowl",
    "olivier": "olivier russian salad",
    "soup": "homemade soup bowl",
    "borscht": "borscht beetroot soup",
    "dumplings": "dumplings pierogi ravioli",
    "golubtsy": "cabbage rolls dish",
    "puree": "mashed potato bowl",
    "buckwheat": "buckwheat porridge bowl",
    "pancakes": "pancakes breakfast",
    "syrniki": "syrniki cheese pancakes",
    "waffle": "waffle dessert",
    "cheese": "cheese plate",
    "kolbasa": "sausage salami slices",
    "bread": "fresh bread loaf",
    "pie": "homemade pie slice",
    "bun": "fresh bakery bun",
    "bagel": "bagel bakery",
    "chips": "potato chips bowl",
    "popcorn": "popcorn bowl cinema",
    "nuts": "mixed nuts snack",
    "cake": "cake dessert slice",
    "cheesecake": "cheesecake dessert slice",
    "tiramisu": "tiramisu dessert",
    "icecream": "ice cream gelato",
    "chocolate": "chocolate bar pieces",
    "candy": "colorful candy sweets",
    "lollipop": "lollipop candy",
    "donut": "donut doughnut glazed",
    "cookie": "cookies biscuit dessert",
    "cupcake": "cupcake muffin dessert",
    "croissant": "croissant bakery",
    "macaron": "macarons dessert",
    "eclair": "eclair pastry dessert",
    "honey": "honey jar honeycomb",
    "jam": "jam jar fruit preserve",
    "zefir": "zephyr marshmallow dessert",
    "halva": "halva oriental dessert",
    "pryanik": "gingerbread cookie",
    "marmalade": "fruit marmalade jelly candy",
    "marshmallow": "marshmallow sweets",
    "gum": "chewing gum",
    "banana": "banana fruit",
    "strawberry": "fresh strawberries",
    "raspberry": "fresh raspberries",
    "blueberry": "fresh blueberries",
    "cherry": "fresh cherries",
    "watermelon": "watermelon fruit slice",
    "melon": "melon fruit slice",
    "apple": "fresh apple fruit",
    "pear": "fresh pear fruit",
    "plum": "fresh plums fruit",
    "peach": "fresh peach fruit",
    "apricot": "fresh apricots fruit",
    "orange": "fresh orange citrus fruit",
    "lemon": "fresh lemon citrus",
    "grapes": "fresh grapes bunch",
    "kiwi": "fresh kiwi fruit",
    "pineapple": "fresh pineapple fruit",
    "mango": "fresh mango fruit",
    "coconut": "fresh coconut fruit",
    "pomegranate": "fresh pomegranate fruit",
    "persimmon": "fresh persimmon fruit",
    "rose": "red roses bouquet",
    "tulips": "tulips bouquet",
    "peony": "pink peony flowers",
    "sunflowers": "sunflowers bouquet",
    "chamomile": "chamomile daisy flowers",
    "carnation": "carnation flower bouquet",
    "chrysanthemum": "chrysanthemum bouquet",
    "lilac": "lilac flowers spring",
    "mimosa": "yellow mimosa flowers",
    "lily_valley": "lily of the valley flowers",
    "orchid": "orchid flowers bouquet",
    "lily": "lily flowers bouquet",
    "cactus": "cactus plant pot",
    "flowers": "beautiful flower bouquet",
    "gift": "wrapped gift present box",
    "teddy": "teddy bear plush toy",
    "jewelry": "jewelry ring necklace",
    "perfume": "perfume bottle fragrance",
    "balloon": "colorful balloons celebration",
    "postcard": "postcard greeting card",
    "book": "book reading",
    "ticket": "concert event ticket",
    "money": "cash banknotes money",
    "car": "car vehicle keys",
    "socks": "cozy socks",
    "slippers": "home slippers",
    "mug": "ceramic coffee mug cup",
    "tshirt": "tshirt clothing",
    "watch": "wrist watch",
    "phone": "smartphone mobile phone",
    "bike": "bicycle bike",
    "scooter": "kick scooter",
    "guitar": "acoustic guitar instrument",
    "ball": "football soccer ball",
    "crown": "golden crown",
    "medal": "medal award",
    "cup_award": "trophy cup award",
    "star": "star night sky",
    "pillow": "pillow bed",
    "blanket": "cozy blanket",
    "candle": "candle warm light",
    "tree": "decorated christmas tree",
    "umbrella": "umbrella rain",
    "headphones": "headphones music",
    "cat": "funny cats",
    "dog": "cute dogs puppies",
    "hamster": "cute hamster pet",
    "parrot": "colorful parrot bird",
    "bunny": "cute rabbit bunny",
    "fish_pet": "aquarium fish goldfish",
    "madhouse": "ambulance emergency hospital",
    "ambulance": "ambulance emergency medical",
    "taxi": "yellow taxi cab city",
    "firefighters": "fire truck firefighters",
}

# Для предметных действий — точные обязательные группы.
# Для каждого Action ниже будет создан профиль, даже если он не имеет
# специального override: тогда primary-группа строится из его тегов.
PIXABAY_REQUIRED_OVERRIDES = {
    "milk": (("milk",), ("glass", "bottle", "carton")),
    "kefir": (("kefir",), ("glass", "bottle", "yogurt", "drink")),
    "water": (("water",), ("glass", "bottle")),
    "coffee": (("coffee", "espresso", "cappuccino", "latte"), ("cup", "mug", "glass")),
    "tea": (("tea",), ("cup", "teapot", "mug")),
    "beer": (("beer", "ale", "lager"), ("glass", "mug", "bottle")),
    "wine": (("wine",), ("glass", "bottle")),
    "champagne": (("champagne", "sparkling"), ("glass", "bottle")),
    "gin": (("gin",), ("tonic", "glass", "cocktail")),
    "tequila": (("tequila",), ("shot", "glass", "lime")),
    "cocktail": (("cocktail",), ("glass", "drink")),
    "martini": (("martini",), ("glass", "cocktail")),
    "mojito": (("mojito",), ("mint", "cocktail", "glass")),
    "aperol": (("aperol", "spritz"), ("glass", "orange", "cocktail")),
    "sake": (("sake",), ("japanese", "rice", "bottle", "cup")),
    "cider": (("cider",), ("apple", "bottle", "glass")),
    "mulled_wine": (("mulled", "wine"), ("spice", "cinnamon", "glass", "mug")),
    "mead": (("mead",), ("honey", "drink", "bottle", "glass")),
    "tincture": (("tincture",), ("bottle", "herbal", "liquor")),
    "liqueur": (("liqueur",), ("bottle", "glass")),
    "milkshake": (("milkshake",), ("glass", "drink")),
    "bubble_tea": (("bubble", "boba"), ("tea", "cup", "drink")),
    "kvass": (("kvass",), ("bottle", "drink")),
    "compote": (("compote",), ("glass", "drink", "berry")),
    "pizza": (("pizza",),), "burger": (("burger", "hamburger", "cheeseburger"),),
    "fries": (("fries", "french fries"),), "hotdog": (("hot dog", "hotdog"),),
    "shawarma": (("shawarma", "kebab"),), "sushi": (("sushi", "maki"),),
    "ramen": (("ramen",),), "pasta": (("pasta", "spaghetti"),),
    "lasagna": (("lasagna",),), "steak": (("steak",),),
    "chicken": (("chicken", "poultry"),), "meat": (("meat", "barbecue", "bbq"),),
    "cutlet": (("cutlet", "meatball"),), "sausages": (("sausage",),),
    "bacon": (("bacon",),), "eggs": (("egg", "eggs", "omelette"),),
    "fish": (("fish", "salmon"),), "herring": (("herring",),),
    "caviar": (("caviar",),), "shrimp": (("shrimp", "prawn"),),
    "taco": (("taco",),), "burrito": (("burrito",),),
    "sandwich": (("sandwich", "toast"),), "salad": (("salad",),),
    "olivier": (("olivier",),), "soup": (("soup", "broth"),),
    "borscht": (("borscht",),), "dumplings": (("dumpling", "pierogi", "ravioli"),),
    "golubtsy": (("cabbage roll", "cabbage", "golubtsy"),), "puree": (("mashed", "puree"),),
    "buckwheat": (("buckwheat",),), "pancakes": (("pancake", "crepe"),),
    "syrniki": (("syrniki", "cheese pancake"),), "waffle": (("waffle",),),
    "cheese": (("cheese",),), "kolbasa": (("sausage", "salami"),),
    "bread": (("bread", "loaf"),), "pie": (("pie",),), "bun": (("bun",),),
    "bagel": (("bagel",),), "chips": (("chips", "crisps"),),
    "popcorn": (("popcorn",),), "nuts": (("nuts", "peanut"),),
    "cake": (("cake",),), "cheesecake": (("cheesecake",),),
    "tiramisu": (("tiramisu",),), "icecream": (("ice cream", "icecream", "gelato"),),
    "chocolate": (("chocolate",),), "candy": (("candy", "sweets"),),
    "lollipop": (("lollipop",),), "donut": (("donut", "doughnut"),),
    "cookie": (("cookie", "biscuit"),), "cupcake": (("cupcake", "muffin"),),
    "croissant": (("croissant",),), "macaron": (("macaron",),),
    "eclair": (("eclair",),), "honey": (("honey",),), "jam": (("jam", "preserve"),),
    "zefir": (("marshmallow", "zephyr"),), "halva": (("halva",),),
    "pryanik": (("gingerbread",),), "marmalade": (("marmalade", "jelly"),),
    "marshmallow": (("marshmallow",),), "gum": (("chewing gum", "gum"),),
}

# Простые предметы/цветы/животные — тоже имеют отдельную смысловую группу.
for _action in ACTIONS:
    if _action.key not in PIXABAY_REQUIRED_OVERRIDES:
        _terms = tuple(t for t in _action.tags if t)
        if _terms:
            PIXABAY_REQUIRED_OVERRIDES[_action.key] = (_terms,)

PIXABAY_CATEGORY_BY_ACTION = {
    **{k: "food" for k in [
        "beer","wine","champagne","whiskey","cognac","vodka","moonshine","rum","gin","tequila","cocktail","martini","mojito","aperol","sake","cider","mulled_wine","mead","tincture","liqueur",
        "coffee","tea","cocoa","matcha","juice","smoothie","cola","lemonade","energy","water","milkshake","bubble_tea","kvass","compote","milk","kefir",
        "pizza","burger","fries","hotdog","shawarma","sushi","ramen","pasta","lasagna","steak","chicken","meat","cutlet","sausages","bacon","eggs","fish","herring","caviar","shrimp","taco","burrito","sandwich","salad","olivier","soup","borscht","dumplings","golubtsy","puree","buckwheat","pancakes","syrniki","waffle","cheese","kolbasa","bread","pie","bun","bagel","chips","popcorn","nuts",
        "cake","cheesecake","tiramisu","icecream","chocolate","candy","lollipop","donut","cookie","cupcake","croissant","macaron","eclair","honey","jam","zefir","halva","pryanik","marmalade","marshmallow","gum",
    ]},
    **{k: "nature" for k in ["banana","strawberry","raspberry","blueberry","cherry","watermelon","melon","apple","pear","plum","peach","apricot","orange","lemon","grapes","kiwi","pineapple","mango","coconut","pomegranate","persimmon","rose","tulips","peony","sunflowers","chamomile","carnation","chrysanthemum","lilac","mimosa","lily_valley","orchid","lily","cactus","flowers","tree"]},
    **{k: "animals" for k in ["cat","dog","hamster","parrot","bunny","fish_pet","teddy"]},
    "ambulance":"transportation", "taxi":"transportation", "firefighters":"transportation",
    "madhouse":"health", "car":"transportation", "bike":"transportation", "scooter":"transportation", "ball":"sports", "gym":"sports", "fishing":"sports", "guitar":"music", "headphones":"music", "phone":"computer",
    "jewelry":"fashion", "perfume":"fashion", "tshirt":"fashion", "watch":"fashion", "socks":"fashion", "slippers":"fashion", "umbrella":"fashion",
    "book":"education", "ticket":"travel", "money":"business", "medal":"sports", "cup_award":"sports",
}


# ---------------------------------------------------------
# Ручная настройка поиска владельцем из панели.
#
# {ключ действия: {"query": "...", "required": [[...], ...], "excluded": [...]}}
# Хранится в настройках всего бота (chat_id = 0). Любое изменение
# меняет отпечаток профиля — бот сам начинает новую коллекцию,
# и старые неподходящие картинки перестают показываться.
# ---------------------------------------------------------

_OVERRIDES: dict[str, dict] = {}


def set_pixabay_overrides(data: dict | None) -> None:
    _OVERRIDES.clear()
    _OVERRIDES.update(data or {})


def pixabay_override(key: str) -> dict:
    return _OVERRIDES.get(key) or {}


def parse_words(text: str) -> list[str]:
    """«cake, layer cake» → ["cake", "layer cake"] (английские слова и фразы)."""
    return [w.strip().lower() for w in (text or "").replace(";", ",").split(",") if w.strip()][:30]


def parse_groups(text: str) -> list[list[str]]:
    """
    Обязательные слова: внутри группы — «любое из» через запятую,
    группы через «;» — «и то, и другое».
    «cake, cakes; slice, dessert» → нужно (cake ИЛИ cakes) И (slice ИЛИ dessert).
    """
    groups = []
    for part in (text or "").split(";"):
        words = [w.strip().lower() for w in part.split(",") if w.strip()]
        if words:
            groups.append(words[:20])
    return groups[:5]


def get_search_query(action: Action, pair_key: str) -> str:
    own = pixabay_override(action.key).get("query")
    if own:
        return own

    """Только внутренний английский Pixabay query, привязанный к Action."""
    if action.category == "pair":
        return PAIR_SEARCHES.get(pair_key, PAIR_SEARCHES["neutral"]).get(
            action.key,
            PIXABAY_QUERY_OVERRIDES.get(action.key, action.search),
        )
    return PIXABAY_QUERY_OVERRIDES.get(action.key, action.search)


def pixabay_required_groups(action: Action, pair_key: str) -> tuple[tuple[str, ...], ...]:
    own = pixabay_override(action.key).get("required")
    if own:
        return tuple(tuple(group) for group in own if group)

    groups = list(PIXABAY_REQUIRED_OVERRIDES.get(action.key, ()))
    if action.category == "pair":
        groups.append(("people", "person", "man", "woman", "couple", "friends", "friend"))
    return tuple(groups)


PIXABAY_GENERIC_EXCLUDE = (
    "illustration", "drawing", "vector", "cartoon", "anime",
    "logo", "icon", "clipart", "sketch", "3d render", "3d",
    "cgi", "digital art", "ai generated", "ai-generated", "artificial intelligence",
    "text", "typography", "poster", "watermark", "meme",
)

# Категориальный мусор. Это именно фильтры импорта из Pixabay, а не
# пользовательские триггеры. Пользовательские команды и русские алиасы
# вообще не участвуют в поиске.
PIXABAY_CATEGORY_EXCLUDE = {
    "alcohol": (
        "non alcoholic", "alcohol free", "mocktail", "juice", "soda",
        "toy", "prop", "plastic", "empty label", "advertisement",
    ),
    "drink": (
        "toy", "plastic", "empty cup", "advertisement", "mockup",
    ),
    "food": (
        "toy", "plastic", "fake food", "recipe card", "advertisement",
        "menu", "packaging mockup", "3d food",
    ),
    "sweet": (
        "toy", "plastic", "fake food", "advertisement", "menu",
        "packaging mockup",
    ),
    "fruit": (
        "toy", "plastic", "fake fruit", "advertisement", "packaging mockup",
    ),
    "flower": (
        "artificial flower", "fake flower", "plastic flower", "paper flower",
        "flower drawing", "flower illustration", "toy",
    ),
    "gift": (
        "illustration", "drawing", "vector", "toy", "plastic", "mockup",
        "advertisement", "product render",
    ),
    "pet": (
        "toy", "plush", "stuffed animal", "statue", "figurine", "sculpture",
        "illustration", "drawing", "vector", "cartoon", "costume",
    ),
    "call": (
        "toy", "model", "miniature", "illustration", "drawing", "vector",
        "cartoon", "advertisement", "logo", "icon",
    ),
    "pair": (
        "mannequin", "statue", "sculpture", "wax figure", "doll", "figurine",
        "illustration", "drawing", "vector", "cartoon", "anime", "avatar",
        "silhouette", "costume", "cosplay", "advertisement",
    ),
}

# Для парных действий одного слова ``people`` недостаточно. Для предметных
# действий требуется собственный смысловой тег. Группы работают по принципу
# AND между группами и OR внутри группы.
PIXABAY_PAIR_PEOPLE = (
    "people", "person", "man", "woman", "couple", "friends", "friend",
)

PIXABAY_ACTION_REQUIRED_GROUPS = {
    # Особенно легко получить нерелевантную фотографию из-за слишком
    # коротких/общих тегов.
    "milk": (("milk",), ("glass", "bottle", "carton", "drink")),
    "kefir": (("kefir",), ("drink", "bottle", "glass", "yogurt")),
    "water": (("water",), ("glass", "bottle", "drink")),
    "coffee": (("coffee", "espresso", "cappuccino", "latte"), ("cup", "coffee")),
    "tea": (("tea",), ("cup", "teapot", "drink")),
    "beer": (("beer", "ale", "lager"), ("glass", "mug", "bottle", "pub")),
    "wine": (("wine",), ("glass", "bottle", "drink")),
    "champagne": (("champagne", "sparkling"), ("glass", "bottle", "toast")),
    "pizza": (("pizza",),),
    "burger": (("burger", "hamburger", "cheeseburger"),),
    "pancakes": (("pancake", "pancakes", "crepe"),),
    "waffle": (("waffle",),),
    "soup": (("soup", "broth"),),
    "borscht": (("borscht",),),
    "cake": (("cake", "cakes"),),
    "icecream": (("ice cream", "icecream", "gelato"),),
    "chocolate": (("chocolate",),),
    "banana": (("banana",),),
    "strawberry": (("strawberry", "strawberries"),),
    "raspberry": (("raspberry", "raspberries"),),
    "rose": (("rose", "roses"),),
    "tulips": (("tulip", "tulips"),),
    "flowers": (("flower", "flowers", "bouquet"),),
    "cat": (("cat", "cats", "kitten", "kittens", "kitty"),),
    "dog": (("dog", "dogs", "puppy", "puppies"),),
    "hamster": (("hamster",),),
    "parrot": (("parrot",),),
    "bunny": (("rabbit", "bunny", "bunnies"),),
    "fish_pet": (("fish", "goldfish", "aquarium"),),
    "gift": (("gift", "present"),),
    "money": (("money", "cash", "banknote", "banknotes", "bills"),),
    "ambulance": (("ambulance",),),
    "taxi": (("taxi", "cab"),),
    "firefighters": (("firefighter", "firefighters", "fire truck", "fire engine"),),
    "madhouse": (("ambulance", "emergency", "psychiatric", "hospital"),),
}

PIXABAY_CALL_CATEGORY = {
    "ambulance": "transportation",
    "taxi": "transportation",
    "firefighters": "transportation",
    "madhouse": "health",
}


def pixabay_profile(action: Action, pair_key: str) -> tuple[str, tuple[str, ...], tuple[str, ...], dict]:
    """Строгий профиль Pixabay для конкретного Action.

    Все 205 Actions получают отдельный профиль: английский query,
    обязательные смысловые группы, категорию Pixabay и blacklist.
    """
    query = get_search_query(action, pair_key)
    required = tuple(required_tags(action))
    excluded = tuple(dict.fromkeys(
        tuple(excluded_tags(action))
        + tuple(pixabay_override(action.key).get("excluded") or ())
        + PIXABAY_GENERIC_EXCLUDE
        + PIXABAY_CATEGORY_EXCLUDE.get(action.category, ())
    ))

    category = PIXABAY_CATEGORY_BY_ACTION.get(action.key)
    if category is None and action.category == "pair":
        category = "people"

    groups = pixabay_required_groups(action, pair_key)

    filters = {
        "category": category,
        "orientation": "horizontal",
        "order": "popular",
        "editors_choice": True,
        "safesearch": True,
        "min_width": 1000,
        "min_height": 750,
        "required_groups": groups,
    }
    return query, required, excluded, filters


def query_variants(query: str) -> list[str]:
    """Строгий режим: не ослабляем запрос до одного случайного слова."""
    query = " ".join(query.split()).strip()
    return [query] if query else []


def rules_version(action: Action, pair_key: str = "neutral") -> str:
    """Отпечаток полного Pixabay-профиля Action + pair variant."""
    query = get_search_query(action, pair_key)
    groups = pixabay_required_groups(action, pair_key)
    category = PIXABAY_CATEGORY_BY_ACTION.get(action.key, "")
    payload = repr((
        query,
        pair_key,
        category,
        groups,
        tuple(required_tags(action)),
        tuple(excluded_tags(action)),
        tuple(PIXABAY_CATEGORY_EXCLUDE.get(action.category, ())),
        repr(sorted(pixabay_override(action.key).items())),
    ))
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()
    return digest[:10]


def collection_key(provider: str, action: Action, pair_key: str) -> str:
    base = action.key

    if action.category == "pair":
        base = f"{action.key}:{pair_key}"

    return f"{provider}/{base}#{rules_version(action, pair_key)}"



logger = logging.getLogger("maruska.images")

@dataclass
class Picked:
    """
    Что вернул подбор картинки.

    cached — уже лежит в Telegram, отправляем по file_id.
    fresh  — только что скачали, отправляем байтами и запоминаем
             полученный file_id.
    """
    kind: str
    collection: str
    provider: str = "pixabay"
    photo_id: str = ""
    file_id: str | None = None
    content: bytes | None = None
    image_id: int | None = None
    photographer_name: str | None = None
    photographer_url: str | None = None
    source_url: str | None = None


# Сколько страниц источника считаем доступными для случайного выбора
MAX_RANDOM_PAGE = 6

# Сколько картинок пробуем скачать, прежде чем сдаться
DOWNLOAD_ATTEMPTS = 3


async def fetch_fresh(
    provider: str,
    action: Action,
    collection: str,
    pair_key: str,
) -> Picked | None:
    """
    Ищет картинку в источнике и сразу скачивает её.

    Ссылки Pixabay живут около суток, поэтому между поиском и
    отправкой не должно проходить времени.
    """
    query, tags, banned, filters = pixabay_profile(action, pair_key)

    seen = await known_photo_ids(collection)

    variants = query_variants(query)

    for tag in tags[:2]:
        if tag not in variants:
            variants.append(tag)

    for variant in variants:
        page = random.randint(1, MAX_RANDOM_PAGE)

        try:
            photos = await search_photos(
                provider,
                variant,
                page,
                required=tags,
                excluded=banned,
                filters=filters,
            )
        except Exception as error:
            logger.error("IMAGE %s SEARCH ERROR: %s %s", provider.upper(), type(error).__name__, error)
            continue

        if not photos:
            continue

        # Сначала то, чего ещё не показывали
        fresh_first = [p for p in photos if p.photo_id not in seen]
        candidates = fresh_first or photos

        random.shuffle(candidates)

        for photo in candidates[:DOWNLOAD_ATTEMPTS]:
            content = await download_photo(photo.image_url, photo.fallback_url)

            if not content:
                continue

            return Picked(
                kind="fresh",
                collection=collection,
                provider=photo.provider,
                photo_id=photo.photo_id,
                content=content,
                photographer_name=photo.photographer_name,
                photographer_url=photo.photographer_url,
                source_url=photo.source_url,
            )

    return None


async def get_image_for_action(
    action: Action,
    pair_key: str = "neutral",
) -> Picked | None:
    """
    Порядок такой:

    1. Берём из коллекции то, что уже загружено в Telegram —
       это мгновенно и не тратит запросы к источнику.
    2. Коллекция кончилась — идём в источник и качаем свежую.
    3. Источник молчит — прокручиваем коллекцию по кругу.
    """
    providers = available_providers()

    if not providers:
        logger.error("IMAGE PROVIDERS: ни один источник не настроен")
        return None

    for provider in providers:
        collection = collection_key(provider, action, pair_key)

        cached = await get_cached_action_image(collection)

        if cached is not None:
            return Picked(
                kind="cached",
                collection=collection,
                provider=cached.provider or provider,
                photo_id=cached.photo_id,
                file_id=cached.telegram_file_id,
                image_id=cached.id,
                photographer_name=cached.photographer_name,
                photographer_url=cached.photographer_url,
                source_url=cached.unsplash_url,
            )

        picked = await fetch_fresh(provider, action, collection, pair_key)

        if picked is not None:
            return picked

        # Свежего нет — пускаем по кругу уже собранное
        if await count_cached_images(collection):
            await reset_cached_images(collection)

            cached = await get_cached_action_image(collection)

            if cached is not None:
                return Picked(
                    kind="cached",
                    collection=collection,
                    provider=cached.provider or provider,
                    photo_id=cached.photo_id,
                    file_id=cached.telegram_file_id,
                    image_id=cached.id,
                    photographer_name=cached.photographer_name,
                    photographer_url=cached.photographer_url,
                    source_url=cached.unsplash_url,
                )

    return None
