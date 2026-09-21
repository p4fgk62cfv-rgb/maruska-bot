"""
Магазин: каталог товаров.

Товар — это запись в инвентаре. Он ничего не делает механически,
его ценность в том, что он виден в профиле и его можно подарить.

Добавить товар — одна строка здесь. Цены вынесены сюда же,
чтобы балансировать экономику в одном месте.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Item:
    key: str
    emoji: str
    title: str
    price: int
    category: str
    description: str = ""
    giftable: bool = True


CATEGORIES = {
    "gift": ("🎁", "Подарки"),
    "style": ("🎨", "Для профиля"),
    "special": ("🏆", "Особые"),
    "fun": ("😈", "Приколы"),
    "rare": ("💎", "Редкие"),
}


ITEMS = (
    # 🎁 Подарки — дешёвые, чтобы дарить часто
    Item("flower", "🌹", "Роза", 30, "gift", "Классика, которая всегда к месту"),
    Item("bouquet", "💐", "Букет", 120, "gift", "Когда одной розы мало"),
    Item("cake", "🍰", "Тортик", 80, "gift", "Повод найдётся"),
    Item("coffee", "☕", "Кофе", 40, "gift", "Спасение по утрам"),
    Item("champagne", "🍾", "Шампанское", 200, "gift", "За победу"),
    Item("teddy", "🧸", "Мишка", 150, "gift", "Обнимательный"),
    Item("balloon", "🎈", "Шарик", 25, "gift", "Просто так"),
    Item("chocolate", "🍫", "Шоколадка", 50, "gift", "Маленькая радость"),

    # 🎨 Для профиля — статусные мелочи
    Item("star_badge", "⭐", "Звезда", 300, "style", "Значок в профиле"),
    Item("crown", "👑", "Корона", 900, "style", "Для тех, кто сверху"),
    Item("fire", "🔥", "Огонь", 250, "style", "Горишь — свети"),
    Item("heart", "💖", "Сердце", 200, "style", "Знак симпатии"),
    Item("skull", "💀", "Череп", 400, "style", "Мрачно и стильно"),
    Item("rainbow", "🌈", "Радуга", 350, "style", "Яркий след"),

    # 🏆 Особые — дорогие, за достижения
    Item("trophy", "🏆", "Кубок", 1500, "special", "Символ победы"),
    Item("medal", "🏅", "Медаль", 800, "special", "За заслуги перед чатом"),
    Item("diamond_ring", "💍", "Кольцо", 2500, "special", "Серьёзные намерения"),
    Item("yacht", "🛥", "Яхта", 5000, "special", "Мечта сбылась"),

    # 😈 Приколы — дешёвые и обидные в хорошем смысле
    Item("sock", "🧦", "Носок", 15, "fun", "Тот самый, непарный"),
    Item("brick", "🧱", "Кирпич", 20, "fun", "Тяжёлый подарок"),
    Item("onion", "🧅", "Лук", 10, "fun", "Чтобы поплакал"),
    Item("trash", "🗑", "Мусор", 5, "fun", "От души"),
    Item("clown", "🤡", "Клоун", 100, "fun", "Кто-то заслужил"),
    Item("goose", "🪿", "Гусь", 60, "fun", "Ущипнёт"),

    # 💎 Редкие — очень дорогие, для коллекционеров
    Item("unicorn", "🦄", "Единорог", 7000, "rare", "Почти не встречается"),
    Item("dragon", "🐉", "Дракон", 10000, "rare", "Легенда чата"),
    Item("meteor", "☄️", "Метеорит", 15000, "rare", "Падает раз в жизни"),
)


ITEM_BY_KEY = {item.key: item for item in ITEMS}


def by_category(category: str) -> list[Item]:
    return sorted(
        (item for item in ITEMS if item.category == category),
        key=lambda item: item.price,
    )


def category_title(category: str) -> str:
    emoji, title = CATEGORIES.get(category, ("📦", category))
    return f"{emoji} {title}"


def find(query: str) -> Item | None:
    """
    Поиск товара по ключу или названию — чтобы /buy работал
    и с «роза», и с «flower».
    """
    value = (query or "").strip().lower()

    if not value:
        return None

    if value in ITEM_BY_KEY:
        return ITEM_BY_KEY[value]

    for item in ITEMS:
        if item.title.lower() == value:
            return item

    for item in ITEMS:
        if item.title.lower().startswith(value) and len(value) >= 3:
            return item

    return None
