"""
Таблица действий.

Формат строки:
    A(key, emoji, поисковый запрос, алиасы, категория,
      винительный падеж предмета, творительный, теги)

Алиасы и теги — через "|". Алиас с "=" требует точного совпадения
слова целиком (для коротких и двусмысленных: "тако", "вода", "суп").

Категории определяют, какими фразами описывается действие:
    alcohol  — напоил, забухали, разлил
    drink    — угостил, принёс
    food     — накормил, заказал, приготовил
    sweet    — подсластил жизнь
    fruit    — как еда, но мягче
    flower   — подарил букет
    gift     — подарил, вручил
    pet      — подарил живность
    call     — вызвал (дурку, скорую, такси)
    pair     — совместное действие, у каждого свои фразы
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Action:
    key: str
    emoji: str
    search: str
    aliases: tuple[str, ...]
    category: str
    item_acc: str = ""
    item_instr: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)
    exclude: tuple[str, ...] = field(default_factory=tuple)


def A(key, emoji, search, aliases, category,
      item_acc="", item_instr="", tags="", exclude=""):
    return Action(
        key=key,
        emoji=emoji,
        search=search,
        aliases=tuple(a for a in aliases.split("|") if a),
        category=category,
        item_acc=item_acc,
        item_instr=item_instr,
        tags=tuple(t for t in tags.split("|") if t) or (key,),
        exclude=tuple(e for e in exclude.split("|") if e),
    )


ACTIONS = [

    # =====================================================
    # АЛКОГОЛЬ
    # =====================================================
    A("beer", "🍺", "beer glass pub", "пив", "alcohol",
      "пиво", "пивом", "beer|pub|ale"),
    A("wine", "🍷", "wine glass evening", "=вино|=вина|=вину|=вином|винишк|винца", "alcohol",
      "вино", "вином", "wine|wineglass"),
    A("champagne", "🥂", "champagne toast celebration", "шампан|шампус|игрист", "alcohol",
      "шампанское", "шампанским", "champagne|sparkling"),
    A("whiskey", "🥃", "whiskey glass", "виски|вискар|бурбон", "alcohol",
      "виски", "виски", "whiskey|whisky|bourbon"),
    A("cognac", "🥃", "cognac brandy glass", "коньяк|бренди", "alcohol",
      "коньяк", "коньяком", "cognac|brandy"),
    A("vodka", "🍸", "vodka shot glass", "водк|водочк|беленьк", "alcohol",
      "водку", "водкой", "vodka"),
    A("moonshine", "🥃", "moonshine alcohol homemade", "брага|брагу|самогон|первач", "alcohol",
      "самогон", "самогоном", "moonshine|distill"),
    A("rum", "🥃", "rum alcohol", "=ром|=рома|=рому|=ромом", "alcohol",
      "ром", "ромом", "rum"),
    A("gin", "🍸", "gin tonic", "=джин|=джина|=джину|=джином|джин тоник", "alcohol",
      "джин-тоник", "джин-тоником", "gin|tonic"),
    A("tequila", "🍹", "tequila shot", "текил", "alcohol",
      "текилу", "текилой", "tequila"),
    A("cocktail", "🍹", "cocktail bar colorful", "коктейл", "alcohol",
      "коктейль", "коктейлем", "cocktail|bar"),
    A("martini", "🍸", "martini cocktail", "мартини", "alcohol",
      "мартини", "мартини", "martini|cocktail"),
    A("mojito", "🍹", "mojito mint cocktail", "мохито", "alcohol",
      "мохито", "мохито", "mojito|mint|cocktail"),
    A("aperol", "🍹", "aperol spritz orange cocktail", "апероль|шприц", "alcohol",
      "апероль", "аперолем", "aperol|spritz|cocktail"),
    A("sake", "🍶", "sake japanese rice wine", "саке", "alcohol",
      "саке", "саке", "sake|japanese|rice"),
    A("cider", "🍏", "cider apple drink", "сидр", "alcohol",
      "сидр", "сидром", "cider"),
    A("mulled_wine", "🍷", "mulled wine winter spices", "глинтвейн|глювайн", "alcohol",
      "глинтвейн", "глинтвейном", "mulled|wine|spice"),
    A("mead", "🍯", "mead honey drink", "медовух", "alcohol",
      "медовуху", "медовухой", "mead"),
    A("tincture", "🫗", "tincture herbal liquor bottle", "настойк|наливк", "alcohol",
      "настойку", "настойкой", "tincture|liquor"),
    A("liqueur", "🥃", "liqueur sweet drink", "ликёр|ликер", "alcohol",
      "ликёр", "ликёром", "liqueur"),

    # =====================================================
    # БЕЗАЛКОГОЛЬНОЕ
    # =====================================================
    A("coffee", "☕", "coffee cup cozy", "кофе|кофейк|латте|капучин|раф|эспрессо", "drink",
      "кофе", "кофе", "coffee|espresso|cappuccino|latte"),
    A("tea", "🍵", "tea cup cozy", "=чай|=чаю|=чая|=чаем|чаёк|чаек", "drink",
      "чай", "чаем", "tea|teacup"),
    A("cocoa", "☕", "cocoa hot chocolate mug", "какао", "drink",
      "какао", "какао", "cocoa"),
    A("matcha", "🍵", "matcha green tea latte", "матча|матчу", "drink",
      "матчу", "матчей", "matcha"),
    A("juice", "🧃", "juice orange fresh", "=сок|=сока|=соку|=соком|сочок|фреш", "drink",
      "сок", "соком", "juice"),
    A("smoothie", "🥤", "smoothie fruit drink", "смузи", "drink",
      "смузи", "смузи", "smoothie"),
    A("cola", "🥤", "cola glass", "кола|колу|колы|колой", "drink",
      "колу", "колой", "cola|coke|soda"),
    A("lemonade", "🍋", "lemonade drink", "лимонад", "drink",
      "лимонад", "лимонадом", "lemonade"),
    A("energy", "⚡", "energy drink can", "энергетик|энергос", "drink",
      "энергетик", "энергетиком", "energy|can"),
    A("water", "💧", "water glass fresh", "=вода|=воды|=воду|=водой|водичк", "drink",
      "воду", "водой", "water"),
    A("milkshake", "🥛", "milkshake sweet", "милкшейк|молочный коктейль", "drink",
      "молочный коктейль", "молочным коктейлем", "milkshake|shake"),
    A("bubble_tea", "🧋", "bubble tea boba", "бабл|боба|bubble", "drink",
      "бабл-ти", "бабл-ти", "bubble|boba"),
    A("kvass", "🍺", "kvass drink bottle", "квас", "drink",
      "квас", "квасом", "kvass"),
    A("compote", "🥤", "compote berry drink", "компот|морс", "drink",
      "компот", "компотом", "compote"),
    A("milk", "🥛", "milk glass", "молок|молочк", "drink",
      "молоко", "молоком", "milk"),
    A("kefir", "🥛", "kefir yogurt drink", "кефир|ряженк", "drink",
      "кефир", "кефиром", "kefir|yogurt"),

    # =====================================================
    # ЕДА
    # =====================================================
    A("pizza", "🍕", "pizza delicious", "пицц", "food",
      "пиццу", "пиццей", "pizza"),
    A("burger", "🍔", "burger juicy", "бургер|гамбургер|чизбургер", "food",
      "бургер", "бургером", "burger|hamburger|cheeseburger"),
    A("fries", "🍟", "fries french potato", "=фри|картошк|картофел", "food",
      "картошку фри", "картошкой фри", "fries|french fries",
      "burger|hamburger"),
    A("hotdog", "🌭", "hot dog", "хотдог|хот-дог", "food",
      "хот-дог", "хот-догом", "hot dog|hotdog|sausage"),
    A("shawarma", "🌯", "kebab wrap street food", "шаурм|шаверм|донер", "food",
      "шаурму", "шаурмой", "kebab|street food"),
    A("sushi", "🍣", "sushi japanese", "суши|роллы|роллов", "food",
      "суши", "суши", "sushi|maki|japanese"),
    A("ramen", "🍜", "ramen noodle soup", "рамен", "food",
      "рамен", "раменом", "ramen"),
    A("pasta", "🍝", "pasta italian", "=паста|=пасту|=пасты|спагетти|макарон", "food",
      "пасту", "пастой", "pasta|spaghetti", "alphabet"),
    A("lasagna", "🍲", "lasagna italian baked", "лазань", "food",
      "лазанью", "лазаньей", "lasagna|italian"),
    A("steak", "🥩", "steak grilled", "стейк", "food",
      "стейк", "стейком", "steak|beef",
      "burger|sandwich|fish"),
    A("chicken", "🍗", "chicken fried", "куриц|курочк|крылышк", "food",
      "курицу", "курицей", "chicken|poultry"),
    A("meat", "🥩", "barbecue grilled meat", "=мясо|=мяса|=мясом|мяска|шашлык", "food",
      "шашлык", "шашлыком", "barbecue|bbq"),
    A("cutlet", "🍖", "cutlet meatball homemade", "котлет|тефтел", "food",
      "котлету", "котлетой", "cutlet|meatball",
      "burger|hamburger|sandwich|fries"),
    A("sausages", "🌭", "sausage grilled", "сосиск|сардельк", "food",
      "сосиски", "сосисками", "sausage"),
    A("bacon", "🥓", "bacon fried breakfast", "бекон", "food",
      "бекон", "беконом", "bacon"),
    A("eggs", "🍳", "fried eggs breakfast", "яичниц|омлет|яйц", "food",
      "яичницу", "яичницей", "egg|omelette"),
    A("fish", "🐟", "fish grilled dish", "=рыба|=рыбу|=рыбы|=рыбой|рыбк", "food",
      "рыбу", "рыбой", "fish|salmon"),
    A("herring", "🐟", "herring fish snack", "селёдк|селедк", "food",
      "селёдку", "селёдкой", "herring"),
    A("caviar", "🥄", "caviar delicacy", "икра|икру|икорк", "food",
      "икру", "икрой", "caviar"),
    A("shrimp", "🍤", "shrimp seafood", "кревет", "food",
      "креветки", "креветками", "shrimp|prawn"),
    A("taco", "🌮", "tacos mexican food", "=тако|такос", "food",
      "тако", "тако", "taco|mexican"),
    A("burrito", "🌯", "burrito mexican wrap", "буррит", "food",
      "буррито", "буррито", "burrito|mexican"),
    A("sandwich", "🥪", "sandwich bread", "сэндвич|сендвич|бутерброд|бутер", "food",
      "бутерброд", "бутербродом", "sandwich|toast"),
    A("salad", "🥗", "salad fresh", "салат", "food",
      "салат", "салатом", "salad|vegetable"),
    A("olivier", "🥗", "salad festive table", "оливье", "food",
      "оливье", "оливье", "salad"),
    A("soup", "🍲", "soup homemade", "=суп|=супа|=супу|=супом|супчик", "food",
      "суп", "супом", "soup|broth"),
    A("borscht", "🍲", "borscht beetroot soup", "борщ", "food",
      "борщ", "борщом", "borscht|beetroot"),
    A("dumplings", "🥟", "dumplings homemade", "пельмен|вареник|хинкал", "food",
      "пельмени", "пельменями", "dumpling|ravioli|pierogi"),
    A("golubtsy", "🥬", "cabbage rolls dish", "голубц", "food",
      "голубцы", "голубцами", "cabbage|roll"),
    A("puree", "🥔", "mashed potato dish", "пюре", "food",
      "пюрешку", "пюрешкой", "mashed|puree"),
    A("buckwheat", "🥣", "buckwheat porridge bowl", "гречк|гречнев", "food",
      "гречку", "гречкой", "buckwheat|porridge|groat"),
    A("pancakes", "🥞", "pancakes breakfast sweet", "блинчик|блины|блинам|оладь", "food",
      "блины", "блинами", "pancake|crepe"),
    A("syrniki", "🥞", "cheese pancakes breakfast", "сырник", "food",
      "сырники", "сырниками", "pancake|cheese"),
    A("waffle", "🧇", "waffle dessert sweet", "вафл", "food",
      "вафли", "вафлями", "waffle"),
    A("cheese", "🧀", "cheese plate", "сыр|сырок|сырку", "food",
      "сыр", "сыром", "cheese"),
    A("kolbasa", "🥓", "sausage salami slices", "колбас|салями", "food",
      "колбасу", "колбасой", "sausage|salami"),
    A("bread", "🍞", "bread fresh bakery", "хлеб|батон|буханк", "food",
      "хлеб", "хлебом", "bread|loaf"),
    A("pie", "🥧", "pie homemade baked", "пирог|пирожок|пирожк", "food",
      "пирог", "пирогом", "pie"),
    A("bun", "🥐", "bun bakery sweet", "булочк|булк", "food",
      "булочку", "булочкой", "bun"),
    A("bagel", "🥯", "bagel bakery", "бублик|бейгл", "food",
      "бублик", "бубликом", "bagel"),
    A("chips", "🍟", "chips snack bowl", "чипс", "food",
      "чипсы", "чипсами", "chips|crisps"),
    A("popcorn", "🍿", "popcorn bowl cinema", "попкорн", "food",
      "попкорн", "попкорном", "popcorn"),
    A("nuts", "🥜", "nuts snack bowl", "орешк|орехи|арахис|фисташк", "food",
      "орешки", "орешками", "nuts|peanut"),

    # =====================================================
    # СЛАДКОЕ
    # =====================================================
    A("cake", "🍰", "cake beautiful", "торт|тортик", "sweet",
      "торт", "тортом", "cake"),
    A("cheesecake", "🍰", "cheesecake dessert slice", "чизкейк", "sweet",
      "чизкейк", "чизкейком", "cheesecake|cake"),
    A("tiramisu", "🍮", "tiramisu dessert", "тирамису", "sweet",
      "тирамису", "тирамису", "tiramisu"),
    A("icecream", "🍦", "icecream dessert", "морожен|пломбир", "sweet",
      "мороженое", "мороженым", "ice cream|icecream|gelato"),
    A("chocolate", "🍫", "chocolate sweet", "шоколад|шоколадк", "sweet",
      "шоколадку", "шоколадкой", "chocolate|cocoa"),
    A("candy", "🍬", "candy sweets colorful", "конфет", "sweet",
      "конфеты", "конфетами", "candy|sweets|lollipop"),
    A("lollipop", "🍭", "lollipop candy", "леденц|леденец|чупа", "sweet",
      "леденец", "леденцом", "lollipop|candy"),
    A("donut", "🍩", "donut glazed sweet", "пончик|донат", "sweet",
      "пончик", "пончиком", "donut|doughnut"),
    A("cookie", "🍪", "cookies homemade sweet", "печенье|печеньк|печеньем", "sweet",
      "печенье", "печеньем", "cookie|biscuit"),
    A("cupcake", "🧁", "cupcake muffin", "капкейк|кекс|маффин", "sweet",
      "капкейк", "капкейком", "cupcake|muffin"),
    A("croissant", "🥐", "croissant bakery", "круассан|круасан", "sweet",
      "круассан", "круассаном", "croissant"),
    A("macaron", "🍬", "macarons colorful dessert", "макарун|макаронс", "sweet",
      "макаруны", "макарунами", "macaron"),
    A("eclair", "🍫", "eclair dessert pastry", "эклер", "sweet",
      "эклер", "эклером", "eclair"),
    A("honey", "🍯", "honey jar golden", "мёд|мед|медок", "sweet",
      "мёд", "мёдом", "honey"),
    A("jam", "🍓", "jam jar homemade", "варень|джем", "sweet",
      "варенье", "вареньем", "jam|preserve"),
    A("zefir", "🍥", "marshmallow sweet dessert", "зефир|пастил", "sweet",
      "зефир", "зефиром", "marshmallow"),
    A("halva", "🍯", "halva oriental sweet", "халв", "sweet",
      "халву", "халвой", "halva|oriental"),
    A("pryanik", "🍪", "gingerbread cookie sweet", "пряник|пряничк", "sweet",
      "пряник", "пряником", "gingerbread|cookie"),
    A("marmalade", "🍬", "marmalade jelly candy", "мармелад", "sweet",
      "мармелад", "мармеладом", "marmalade|jelly"),
    A("marshmallow", "🍡", "marshmallow sweet", "маршмеллоу|маршмелл", "sweet",
      "маршмеллоу", "маршмеллоу", "marshmallow|candy"),
    A("gum", "🍬", "chewing gum", "жвачк|жевачк", "sweet",
      "жвачку", "жвачкой", "chewing gum|gum"),

    # =====================================================
    # ФРУКТЫ И ЯГОДЫ
    # =====================================================
    A("banana", "🍌", "banana fruit yellow", "банан", "fruit",
      "банан", "бананом", "banana"),
    A("strawberry", "🍓", "strawberries fresh", "клубник", "fruit",
      "клубнику", "клубникой", "strawberr"),
    A("raspberry", "🍇", "raspberries berries fresh", "малин", "fruit",
      "малину", "малиной", "raspberr"),
    A("blueberry", "🫐", "blueberries berries fresh", "черник|голубик", "fruit",
      "чернику", "черникой", "blueberr"),
    A("cherry", "🍒", "cherries fresh red", "вишн|черешн", "fruit",
      "вишню", "вишней", "cherr"),
    A("watermelon", "🍉", "watermelon slice", "арбуз", "fruit",
      "арбуз", "арбузом", "watermelon"),
    A("melon", "🍈", "melon slice sweet", "дын", "fruit",
      "дыню", "дыней", "melon"),
    A("apple", "🍎", "apple red", "яблок|яблоч", "fruit",
      "яблоко", "яблоком", "apple"),
    A("pear", "🍐", "pear fruit", "груш", "fruit",
      "грушу", "грушей", "pear"),
    A("plum", "🍇", "plums fruit purple", "слив", "fruit",
      "сливу", "сливой", "plum"),
    A("peach", "🍑", "peach fruit", "персик", "fruit",
      "персик", "персиком", "peach"),
    A("apricot", "🍑", "apricots fruit", "абрикос|урюк", "fruit",
      "абрикосы", "абрикосами", "apricot"),
    A("orange", "🍊", "orange fruit citrus", "апельсин|мандарин", "fruit",
      "апельсин", "апельсином", "orange|tangerine"),
    A("lemon", "🍋", "lemon citrus fruit", "лимон", "fruit",
      "лимон", "лимоном", "lemon"),
    A("grapes", "🍇", "grapes fruit", "виноград", "fruit",
      "виноград", "виноградом", "grape"),
    A("kiwi", "🥝", "kiwi fruit slice", "киви", "fruit",
      "киви", "киви", "kiwi"),
    A("pineapple", "🍍", "pineapple fruit", "ананас", "fruit",
      "ананас", "ананасом", "pineapple"),
    A("mango", "🥭", "mango fruit tropical", "манго", "fruit",
      "манго", "манго", "mango"),
    A("coconut", "🥥", "coconut tropical", "кокос", "fruit",
      "кокос", "кокосом", "coconut"),
    A("pomegranate", "🍎", "pomegranate fruit red", "гранат", "fruit",
      "гранат", "гранатом", "pomegranate"),
    A("persimmon", "🍊", "persimmon fruit orange", "хурм", "fruit",
      "хурму", "хурмой", "persimmon"),

    # =====================================================
    # ЦВЕТЫ
    # =====================================================
    A("rose", "🌹", "roses bouquet red", "=розы|=розу|=роз|розочк", "flower",
      "букет роз", "букетом роз", "rose"),
    A("tulips", "🌷", "tulips bouquet", "тюльпан", "flower",
      "букет тюльпанов", "букетом тюльпанов", "tulip"),
    A("peony", "🌸", "peonies bouquet pink", "пион", "flower",
      "букет пионов", "букетом пионов", "peon|flower"),
    A("sunflowers", "🌻", "sunflowers bouquet", "подсолнух", "flower",
      "букет подсолнухов", "букетом подсолнухов", "sunflower"),
    A("chamomile", "🌼", "chamomile daisy flowers", "ромашк", "flower",
      "ромашки", "ромашками", "chamomile|daisy|flower"),
    A("carnation", "🌺", "carnation flowers bouquet", "гвоздик", "flower",
      "гвоздики", "гвоздиками", "carnation|flower"),
    A("chrysanthemum", "🌼", "chrysanthemum flowers bouquet", "хризантем", "flower",
      "хризантемы", "хризантемами", "chrysanthemum|flower"),
    A("lilac", "💜", "lilac flowers spring", "сирень|сирен", "flower",
      "сирень", "сиренью", "lilac|flower|spring"),
    A("mimosa", "💛", "mimosa flowers yellow", "мимоз", "flower",
      "мимозу", "мимозой", "mimosa|flower|yellow"),
    A("lily_valley", "🌸", "lily of the valley flowers", "ландыш", "flower",
      "ландыши", "ландышами", "lily|valley|flower"),
    A("orchid", "🌺", "orchid flowers bouquet", "орхиде", "flower",
      "орхидею", "орхидеей", "orchid"),
    A("lily", "🌸", "lilies bouquet", "лилии|лилию|лилий", "flower",
      "лилии", "лилиями", "lily|lilies"),
    A("cactus", "🌵", "cactus plant pot", "кактус", "flower",
      "кактус", "кактусом", "cactus|succulent"),
    A("flowers", "💐", "flowers bouquet beautiful", "цветы|цветочк|цветок|букет", "flower",
      "букет цветов", "букетом цветов", "flower|bouquet|blossom"),

    # =====================================================
    # ПОДАРКИ И ПРЕДМЕТЫ
    # =====================================================
    A("gift", "🎁", "gift present wrapped", "подар|презент", "gift",
      "подарок", "подарком", "gift"),
    A("teddy", "🧸", "teddy bear cute", "мишк|мишку|плюшев", "gift",
      "мишку", "мишкой", "teddy|bear|plush"),
    A("jewelry", "💎", "jewelry elegant gift", "украшен|ювелир|колечк|кольцо", "gift",
      "украшение", "украшением", "jewel|ring|necklace|diamond"),
    A("perfume", "🧴", "perfume bottle elegant", "духи|парфюм", "gift",
      "духи", "духами", "perfume|fragrance"),
    A("balloon", "🎈", "balloons colorful celebration", "шарик|=шар|шарики", "gift",
      "шарики", "шариками", "balloon|party"),
    A("postcard", "💌", "postcard letter handwritten", "открытк|письм", "gift",
      "открытку", "открыткой", "postcard|letter|card"),
    A("book", "📚", "book reading cozy", "книг|книжк", "gift",
      "книгу", "книгой", "book|reading|library"),
    A("ticket", "🎫", "tickets concert event", "билет", "gift",
      "билет", "билетом", "ticket|concert|event"),
    A("money", "💸", "money cash bills", "деньг|денег|бабк|=лям|миллион", "gift",
      "миллион", "миллионом", "money|cash|bills"),
    A("car", "🚗", "car keys new", "машин|тачк|ключи", "gift",
      "ключи от машины", "ключами от машины", "keys|auto"),
    A("socks", "🧦", "socks cozy warm", "носк|носочк", "gift",
      "носки", "носками", "socks"),
    A("slippers", "🥿", "slippers home cozy", "тапочк|тапк", "gift",
      "тапочки", "тапочками", "slipper|home"),
    A("mug", "☕", "mug cup gift", "кружк|чашк", "gift",
      "кружку", "кружкой", "ceramic"),
    A("tshirt", "👕", "tshirt clothes", "футболк|майк", "gift",
      "футболку", "футболкой", "shirt|clothes|apparel"),
    A("watch", "⌚", "watch wrist elegant", "=часы|часики", "gift",
      "часы", "часами", "watch|wrist"),
    A("phone", "📱", "smartphone new device", "телефон|айфон|смартфон", "gift",
      "телефон", "телефоном", "phone|smartphone|mobile"),
    A("bike", "🚲", "bicycle new", "велик|велосипед", "gift",
      "велосипед", "велосипедом", "bicycle|bike|cycling"),
    A("scooter", "🛴", "scooter ride", "самокат", "gift",
      "самокат", "самокатом", "scooter|ride|kick"),
    A("guitar", "🎸", "guitar music instrument", "гитар", "gift",
      "гитару", "гитарой", "guitar|music|instrument"),
    A("ball", "⚽", "football ball sport", "=мяч|мячик|футбол", "gift",
      "мяч", "мячом", "ball|football|soccer"),
    A("crown", "👑", "crown golden royal", "корон", "gift",
      "корону", "короной", "crown"),
    A("medal", "🏅", "medal award winner", "медал", "gift",
      "медаль", "медалью", "medal"),
    A("cup_award", "🏆", "trophy cup winner", "кубок|кубк|трофе", "gift",
      "кубок", "кубком", "trophy"),
    A("star", "⭐", "star night sky", "звезд|звёзд", "gift",
      "звезду с неба", "звездой с неба", "star|sky|night"),
    A("pillow", "🛏️", "pillow bed cozy", "подушк", "gift",
      "подушку", "подушкой", "pillow|bed"),
    A("blanket", "🛋️", "blanket cozy warm", "плед|одеял", "gift",
      "плед", "пледом", "blanket"),
    A("candle", "🕯️", "candle cozy light", "свечк|свеч", "gift",
      "свечку", "свечкой", "candle"),
    A("tree", "🎄", "christmas tree decorated", "ёлк|елк|ёлочк", "gift",
      "ёлку", "ёлкой", "christmas|tree"),
    A("umbrella", "☂️", "umbrella rain", "зонт", "gift",
      "зонт", "зонтом", "umbrella"),
    A("headphones", "🎧", "headphones music", "наушник", "gift",
      "наушники", "наушниками", "headphone"),

    # =====================================================
    # ЖИВНОСТЬ
    # =====================================================
    A("cat", "🐱", "kitten cute cat", "=кот|котик|котён|котен|кошк", "pet",
      "котика", "котиком", "cat|kitten|kitty"),
    A("dog", "🐶", "puppy cute dog", "щенок|щенк|щеночк|собачк|пёсик|песик", "pet",
      "щенка", "щенком", "dog|puppy"),
    A("hamster", "🐹", "hamster cute pet", "хомяк|хомячк", "pet",
      "хомяка", "хомяком", "hamster|rodent"),
    A("parrot", "🦜", "parrot colorful bird", "попугай|попугайч", "pet",
      "попугая", "попугаем", "parrot|bird"),
    A("bunny", "🐰", "bunny rabbit cute", "кролик|зайчик|зайк", "pet",
      "кролика", "кроликом", "rabbit|bunny"),
    A("fish_pet", "🐠", "aquarium fish colorful", "рыбку|аквариум", "pet",
      "рыбку", "рыбкой", "aquarium|goldfish"),

    # =====================================================
    # ВЫЗОВЫ (шуточные)
    # =====================================================
    A("madhouse", "🚑", "ambulance emergency vehicle", "дурк|психушк|санитар|дурдом", "call",
      "", "", "ambulance|hospital"),
    A("ambulance", "🚑", "ambulance emergency medical", "скорую|скорая|неотложк", "call",
      "", "", "ambulance|medical"),
    A("taxi", "🚕", "taxi car city", "такси|такс", "call",
      "", "", "taxi|cab"),
    A("firefighters", "🚒", "fire truck emergency", "пожарн", "call",
      "", "", "fire|truck"),

    # =====================================================
    # ПАРНЫЕ ДЕЙСТВИЯ
    # =====================================================
    A("hug", "🤗", "hugging friends happy", "обня|обним|обнимашк|обнимаю", "pair",
      "", "", "hug|embrace"),
    A("kiss", "😘", "kissing couple", "поцелу|поцело|целу|чмок", "pair",
      "", "", "kiss"),
    A("carry", "🧸", "carrying piggyback fun happy", "на ручки|на руки|ручки", "pair",
      "", "", "carry|piggyback|lift"),
    A("pat", "🫳", "petting head gentle happy", "погладить|поглажу|гладит|глажу", "pair",
      "", "", "pat|head|gentle"),
    A("tickle", "😂", "tickling laughing fun", "щекот|пощекот", "pair",
      "", "", "tickle|laugh"),
    A("wake", "⏰", "alarm clock morning wake", "разбуд|будить|подъём|подъем", "pair",
      "", "", "alarm|morning"),
    A("lull", "😴", "sleeping cozy night rest", "убаюк|баюшк|колыбельн", "pair",
      "", "", "sleep|rest"),
    A("cover", "🛋️", "blanket cozy warm rest", "укрыть|укутать|укутаю", "pair",
      "", "", "blanket"),
    A("photo", "📸", "photographer camera portrait", "сфоткат|сфотограф|фотка", "pair",
      "", "", "camera|photo|portrait"),
    A("wink", "😉", "wink smile playful portrait", "подмигн|подмигиваю", "pair",
      "", "", "wink|smile|playful"),
    A("sing", "🎤", "singing microphone karaoke", "спеть|спою|песенк|караоке", "pair",
      "", "", "singing|microphone|karaoke"),
    A("praise", "👏", "applause clapping praise", "похвал|молодец|красав", "pair",
      "", "", "applause|clap|praise"),
    A("scold", "😤", "finger wagging serious funny", "поругать|ругаю|ай-яй", "pair",
      "", "", "angry|serious|funny"),
    A("walk_home", "🚶", "walking evening street together", "проводить|провожу|провожать", "pair",
      "", "", "walking|street|evening"),
    A("highfive", "🙌", "high five friends", "дай пять|пятюн|хайфайв|=пять", "pair",
      "", "", "high five|highfive"),
    A("handshake", "🤝", "handshake smiling people", "рукопожат|пожми|жму руку", "pair",
      "", "", "handshake|shaking"),
    A("support", "🫶", "laughing friends together", "поддерж", "pair",
      "", "", "friend|laugh|smil"),
    A("congratulations", "🎉", "celebration confetti happy", "поздрав", "pair",
      "", "", "celebrat|confetti|congrat"),
    A("party", "🥳", "party celebration friends fun", "вечерин|тусов|=праздник", "pair",
      "", "", "party|celebrat"),
    A("movie", "🎬", "movie popcorn cinema", "=кино|фильм", "pair",
      "", "", "movie|popcorn|film"),
    A("music", "🎵", "music headphones happy", "музык|песн", "pair",
      "", "", "music|song"),
    A("dance", "💃", "dancing people happy", "танц|потанц", "pair",
      "", "", "danc"),
    A("banya", "🧖", "sauna spa relax", "баня|баню|банька|сауна", "pair",
      "", "", "sauna|spa|steam"),
    A("fishing", "🎣", "fishing rod lake", "рыбалк|рыбачит", "pair",
      "", "", "fishing|rod|lake"),
    A("gym", "🏋️", "gym workout fitness", "спортзал|качалк|трениров", "pair",
      "", "", "gym|fitness|workout"),
    A("game", "🎮", "gaming console controller", "поиграть|игрануть|катку", "pair",
      "", "", "gaming|console|controller"),
    A("selfie", "🤳", "selfie friends smiling", "селфи", "pair",
      "", "", "selfie"),
    A("sea", "🏖️", "beach sea vacation", "=море|отпуск|=пляж", "pair",
      "", "", "beach|sea|vacation"),
    A("walk", "🌳", "walking park autumn", "прогул|погулять|променад", "pair",
      "", "", "walk|park|outdoor"),
    A("coffee_break", "☕", "coffee break friends talking", "перекур|перерыв", "pair",
      "", "", "coffee|break|talking"),
]


ACTION_BY_KEY = {action.key: action for action in ACTIONS}


# Категории, где сток особенно любит подсунуть не то:
# надпись из макарон вместо супа, рисунок вместо блюда.
EDIBLE = ("alcohol", "drink", "food", "sweet", "fruit")

GLOBAL_FOOD_EXCLUDE = (
    "letters", "letter", "alphabet", "font", "typography",
    "text", "word", "sign", "poster", "menu", "blackboard",
    "drawing", "illustration", "vector", "clipart", "sketch",
    "logo", "icon", "3d", "render",
)


def required_tags(action: Action) -> tuple[str, ...]:
    return action.tags


def excluded_tags(action: Action) -> tuple[str, ...]:
    if action.category in EDIBLE:
        return action.exclude + GLOBAL_FOOD_EXCLUDE

    return action.exclude
