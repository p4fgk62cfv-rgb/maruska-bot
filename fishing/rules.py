"""
Рыбалка — правила игры без базы и без Telegram.

Здесь решается всё, что влияет на награду: какая рыба клюнула,
сколько весит, трофей ли это, сколько алмазов и опыта. Сервер —
единственный, кто это считает: телефон игрока только показывает.

Ключи, названия и картинки совпадают с клиентом (webapp/static/fishing).

Что исправлено по сравнению с автономной версией:
  • рыба выбирается с учётом редкости, а не равновероятно из списка
    водоёма (раньше легендарный таймень попадался в 33% забросов);
  • наживка влияет на то, кто клюёт (раньше только тратилась);
  • ночной улов засчитывается при поимке ночью, а не случайно при забросе;
  • одна таблица цен на наживку вместо двух разных;
  • награды масштабируются под экономику Мары (настройка владельца).
"""

import random
from dataclasses import dataclass
from datetime import timedelta


# ---------------------------------------------------------
# Редкость: относительный вес в розыгрыше внутри водоёма
# ---------------------------------------------------------

RARITY_WEIGHT = {
    "Обычная": 50.0,
    "Необычная": 26.0,
    "Редкая": 12.0,
    "Эпическая": 5.5,
    "Легендарная": 2.0,
    "Мифическая": 0.5,
}

RARE_RANKS = ("Редкая", "Эпическая", "Легендарная", "Мифическая")
LEGEND_RANKS = ("Легендарная", "Мифическая")


@dataclass(frozen=True)
class Fish:
    key: str
    name: str
    rarity: str
    min_w: float
    max_w: float
    power: int
    value: int
    xp: int
    trophy: bool = False


FISH = {f.key: f for f in (
    Fish("pike", "Щука", "Редкая", .8, 8.8, 78, 320, 55, True),
    Fish("perch", "Окунь", "Обычная", .15, 2.1, 35, 90, 24),
    Fish("crucian", "Карась", "Обычная", .12, 1.8, 28, 70, 22),
    Fish("roach", "Плотва", "Обычная", .08, 1.3, 22, 55, 18),
    Fish("carp", "Карп", "Эпическая", 1.5, 12, 82, 620, 95, True),
    Fish("tench", "Линь", "Необычная", .3, 3.4, 48, 180, 42),
    Fish("bream", "Лещ", "Необычная", .4, 4.8, 55, 210, 46),
    Fish("zander", "Судак", "Редкая", .7, 6.2, 68, 390, 62),
    Fish("asp", "Жерех", "Редкая", .8, 5.6, 64, 360, 58),
    Fish("catfish", "Сом", "Легендарная", 3, 25, 96, 1250, 170, True),
    Fish("chub", "Голавль", "Необычная", .4, 3.5, 51, 200, 44),
    Fish("burbo", "Налим", "Редкая", .6, 5.8, 62, 410, 68),
    Fish("trout", "Форель", "Эпическая", .5, 6, 73, 700, 105, True),
    Fish("taimen", "Таймень", "Легендарная", 2, 18, 91, 1600, 220, True),
    Fish("beluga", "Белуга", "Мифическая", 8, 35, 100, 3000, 350),
)}


@dataclass(frozen=True)
class Location:
    key: str
    name: str
    level: int
    fish: tuple[str, ...]
    night: bool = False


LOCATIONS = (
    Location("quiet", "Тихая заводь", 1, ("pike", "perch", "crucian", "roach", "carp")),
    Location("forest", "Лесное озеро", 2, ("pike", "perch", "carp", "tench", "bream")),
    Location("river", "Большая река", 4, ("zander", "asp", "catfish", "bream", "chub")),
    Location("mountain", "Горное озеро", 6, ("trout", "taimen", "perch")),
    Location("deep", "Глубокая вода", 8, ("catfish", "taimen", "beluga", "burbo"), night=True),
)


@dataclass(frozen=True)
class Rod:
    key: str
    name: str
    price: int
    control: int
    power: int
    level: int


RODS = {r.key: r for r in (
    Rod("starter", "Простая удочка", 0, 8, 0, 0),
    Rod("float", "Поплавочная", 250, 16, 5, 2),
    Rod("spin", "Спиннинг", 600, 12, 20, 3),
    Rod("feeder", "Фидер", 950, 24, 14, 4),
    Rod("carp", "Карповик", 1500, 18, 35, 6),
    Rod("premium", "Таймень Pro", 3000, 28, 48, 9),
)}

MAX_ROD_LEVEL = 8


# Катушка: добавляет контроль и силу к удочке
@dataclass(frozen=True)
class Reel:
    key: str
    name: str
    price: int
    control: int
    power: int
    level: int


REELS = {r.key: r for r in (
    Reel("basic", "Катушка «Старт»", 0, 0, 0, 0),
    Reel("bronze", "Бронза", 180, 3, 2, 1),
    Reel("forest", "Лесная", 350, 5, 4, 2),
    Reel("aqua", "Аква", 600, 7, 7, 3),
    Reel("flame", "Пламя", 900, 9, 10, 4),
    Reel("amber", "Янтарь", 1400, 12, 14, 6),
    Reel("gold", "Золотая", 2200, 15, 18, 8),
    Reel("amethyst", "Аметист", 3500, 18, 24, 10),
    Reel("crystal", "Кристалл", 5000, 22, 30, 12),
)}


# Поплавок: чувствительность — поклёвка приходит быстрее (sense, доля
# ожидания) и чаще замечается трофей (trophy, прибавка к шансу)
@dataclass(frozen=True)
class Bobber:
    key: str
    name: str
    price: int
    sense: float
    trophy: float
    level: int


BOBBERS = {b.key: b for b in (
    Bobber("wood", "Деревянный", 0, 0.0, 0.0, 0),
    Bobber("classic", "Классика", 80, .05, .005, 1),
    Bobber("reed", "Камыш", 200, .10, .01, 2),
    Bobber("azure", "Лазурь", 400, .15, .015, 3),
    Bobber("night", "Ночной", 700, .20, .02, 5),
    Bobber("royal", "Королевский", 1100, .25, .025, 6),
    Bobber("gold", "Золотой", 1800, .30, .03, 8),
    Bobber("amethyst", "Аметист", 3000, .35, .04, 10),
    Bobber("crystal", "Кристалл", 4500, .40, .05, 12),
)}

BASE_TROPHY = 0.07


def with_reel(rod: "Rod", rod_level: int, reel: Reel) -> "Rod":
    """Удочка с учётом прокачки и катушки — ею считаются шансы и вываживание."""
    return Rod(rod.key, rod.name, rod.price,
               rod.control + (rod_level - 1) * 3 + reel.control,
               rod.power + (rod_level - 1) * 4 + reel.power, rod.level)


def bite_delay(bobber: Bobber, rng=random) -> float:
    return round((0.9 + rng.random() * 2.3) * (1 - bobber.sense), 2)


def catalog() -> dict:
    """Катушки и поплавки для магазина мини-приложения."""
    return {
        "reels": [{"key": r.key, "name": r.name, "price": r.price, "control": r.control,
                   "power": r.power, "level": r.level} for r in REELS.values()],
        "boats": [{"key": b.key, "name": b.name, "price": b.price, "control": b.control,
                   "reward": b.reward, "level": b.level} for b in BOATS.values()],
        "bobbers": [{"key": b.key, "name": b.name, "price": b.price, "sense": round(b.sense * 100),
                     "trophy": round(b.trophy * 100, 1), "level": b.level} for b in BOBBERS.values()],
    }


def upgrade_cost(current_level: int) -> int:
    return 180 * current_level


@dataclass(frozen=True)
class Boat:
    key: str
    name: str
    price: int
    control: int
    reward: float
    level: int


BOATS = {b.key: b for b in (
    # Ключи shore/boat/speedboat/legend — те же, что были у старого флота:
    # купленные лодки у игроков сохраняются.
    Boat("shore", "Деревянная лодка", 0, 0, 0.0, 1),
    Boat("raft", "Надувная лодка", 450, 4, .04, 2),
    Boat("boat", "Алюминиевая лодка", 1200, 8, .08, 4),
    Boat("blue", "Синяя скоростная", 2200, 11, .12, 5),
    Boat("speedboat", "Спортивный катер", 3500, 15, .16, 7),
    Boat("yacht", "Золотая яхта", 5000, 18, .20, 8),
    Boat("airboat", "Аэролодка", 6000, 21, .24, 9),
    Boat("legend", "RIB «Таймень»", 7000, 24, .28, 10),
    Boat("dragon", "Золотой дракон", 12000, 30, .36, 12),
)}


# Наживка: цена за 1 шт. и кому она нравится (множитель веса в розыгрыше)
PREDATORS = ("pike", "zander", "perch", "asp", "catfish", "taimen", "trout", "chub", "burbo")
PEACEFUL = ("crucian", "roach", "carp", "tench", "bream")


@dataclass(frozen=True)
class Bait:
    key: str
    name: str
    price: int
    likes: tuple[str, ...]
    boost: float = 2.5
    free: bool = False


BAITS = {b.key: b for b in (
    Bait("worm", "Червь", 0, PEACEFUL + ("perch", "burbo"), 1.5, free=True),
    Bait("maggots", "Опарыш", 18, PEACEFUL),
    Bait("corn", "Кукуруза", 14, ("carp", "crucian", "bream", "tench")),
    Bait("bread", "Хлеб", 10, ("crucian", "roach", "carp")),
    Bait("livebait", "Живец", 45, ("pike", "zander", "catfish", "burbo", "taimen")),
    Bait("fly", "Мушка", 50, ("trout", "chub", "asp")),
    Bait("wobbler", "Воблер", 65, ("pike", "asp", "zander", "taimen")),
    Bait("spinner", "Блесна", 60, ("perch", "pike", "asp", "trout")),
    Bait("softbait", "Силикон", 55, ("zander", "perch", "pike", "catfish")),
)}

BAIT_PACK = 5


# ---------------------------------------------------------
# Розыгрыш
# ---------------------------------------------------------

def fish_weights(location: Location, rod: Rod, bait: Bait) -> dict[str, float]:
    """
    Шанс каждой рыбы в водоёме. Редкость задаёт основу, наживка
    усиливает «своих» рыб, мощная удочка чуть поднимает крупных.
    """
    weights = {}

    for key in location.fish:
        fish = FISH[key]
        weight = RARITY_WEIGHT[fish.rarity]

        if key in bait.likes:
            weight *= bait.boost

        # Сильная удочка помогает с крупной рыбой, но не делает её частой
        if fish.rarity in RARE_RANKS:
            weight *= 1 + rod.power / 200

        weights[key] = weight

    return weights


def chances(location: Location, rod: Rod, bait: Bait) -> dict[str, float]:
    """Проценты — для панели и для тестов."""
    weights = fish_weights(location, rod, bait)
    total = sum(weights.values()) or 1
    return {key: round(value * 100 / total, 2) for key, value in weights.items()}


def choose_fish(location: Location, rod: Rod, bait: Bait, rng=random) -> Fish:
    weights = fish_weights(location, rod, bait)
    keys = list(weights)
    return FISH[rng.choices(keys, weights=[weights[k] for k in keys], k=1)[0]]


def roll_catch(fish: Fish, rng=random, trophy_chance: float = 0.07) -> tuple[float, bool, int]:
    """Вес, трофей ли, длина в сантиметрах."""
    weight = fish.min_w + rng.random() * (fish.max_w - fish.min_w)
    trophy = fish.trophy and rng.random() < trophy_chance

    if trophy:
        weight = min(fish.max_w, weight * 1.2)

    weight = round(weight, 2)
    length = round(22 + weight * 8 + rng.random() * 14)

    return weight, trophy, length


def catch_reward(fish: Fish, trophy: bool, location_index: int, boat: Boat, reward_percent: int) -> int:
    """
    Алмазы за улов. Базовые цены рассчитаны на отдельную экономику
    игры (до 3000 за рыбу), поэтому владелец масштабирует их процентом.
    """
    base = fish.value * (2.4 if trophy else 1) * (1 + location_index * .08) * (1 + boat.reward)
    return max(0, round(base * reward_percent / 100))


def catch_xp(fish: Fish, trophy: bool, xp_percent: int) -> int:
    base = fish.xp * (1.7 if trophy else 1)
    return max(0, round(base * xp_percent / 100))


def streak_bonus(streak: int, reward_percent: int) -> int:
    """Бонус за серию дней: растёт до недели, дальше не больше."""
    return round(min(streak, 7) * 150 * reward_percent / 100)


# ---------------------------------------------------------
# Энергия: каждый заброс тратит силы, они восстанавливаются со временем
# ---------------------------------------------------------

ENERGY_PER_LEVEL = 2


def energy_cap(level: int, base: int) -> int:
    """Запас растёт с уровнем, но не больше чем в полтора раза."""
    return min(base + ENERGY_PER_LEVEL * max(0, level - 1), round(base * 1.5))


def cast_cost(location_index: int, base: int) -> int:
    """Дальние водоёмы щедрее на награду — и забирают больше сил."""
    return base + location_index


def energy_now(stored: int, at, now, cap: int, regen_seconds: int):
    """
    Текущая энергия и момент, от которого считать следующую единицу.
    Выше запаса энергия не восстанавливается, но и не срезается:
    термос может поднять её над максимумом.
    """
    if stored >= cap:
        return stored, now

    gained = int((now - at).total_seconds() // regen_seconds)
    value = min(cap, stored + gained)

    if value >= cap:
        return cap, now

    return value, at + timedelta(seconds=gained * regen_seconds)


# ---------------------------------------------------------
# Задания дня и достижения
# ---------------------------------------------------------

QUESTS = (
    {"id": "q_catch", "title": "Первый улов", "desc": "Поймай 5 рыб", "target": 5, "reward": 180, "type": "catch"},
    {"id": "q_weight", "title": "Тяжёлый трофей", "desc": "Поймай рыбу тяжелее 4 кг", "target": 1, "reward": 260, "type": "weight"},
    {"id": "q_night", "title": "Ночная охота", "desc": "Поймай 2 рыбы ночью", "target": 2, "reward": 320, "type": "night"},
    {"id": "q_river", "title": "Речная экспедиция", "desc": "Поймай 3 рыбы на Большой реке", "target": 3, "reward": 300, "type": "river"},
    {"id": "q_rare", "title": "Редкая добыча", "desc": "Поймай 2 редкие или ещё реже", "target": 2, "reward": 420, "type": "rare"},
)

QUESTS_PER_DAY = 3


def daily_quests(day: str, user_id: int) -> list[dict]:
    """Три задания на день — у каждого игрока свои, но стабильные в течение дня."""
    rng = random.Random(f"{day}:{user_id}")
    chosen = rng.sample(QUESTS, QUESTS_PER_DAY)
    return [{**q, "progress": 0, "done": False} for q in chosen]


def quest_step(quest: dict, fish: Fish, weight: float, night: bool, location: Location) -> int:
    """На сколько продвинулось задание этим уловом."""
    kind = quest["type"]

    if kind == "catch":
        return 1
    if kind == "weight":
        return 1 if weight >= 4 else 0
    if kind == "night":
        return 1 if night else 0
    if kind == "river":
        return 1 if location.key == "river" else 0
    if kind == "rare":
        return 1 if fish.rarity in RARE_RANKS else 0
    return 0


ACHIEVEMENTS = (
    {"id": "first", "icon": "🐟", "name": "Первая рыба", "desc": "Поймать первую рыбу", "reward": 100},
    {"id": "ten", "icon": "🎣", "name": "Рыбак", "desc": "Поймать 10 рыб", "reward": 250},
    {"id": "collector", "icon": "🗃️", "name": "Коллекционер", "desc": "Открыть 10 видов", "reward": 500},
    {"id": "big", "icon": "⚖️", "name": "Тяжеловес", "desc": "Поймать рыбу 10+ кг", "reward": 700},
    {"id": "legend", "icon": "👑", "name": "Легенда", "desc": "Поймать легендарную рыбу", "reward": 1000},
    {"id": "night", "icon": "🌙", "name": "Ночной охотник", "desc": "Поймать рыбу ночью", "reward": 400},
)


def unlocked_achievements(stats: dict, already: list[str]) -> list[dict]:
    checks = {
        "first": stats.get("caught", 0) >= 1,
        "ten": stats.get("caught", 0) >= 10,
        "collector": len(stats.get("species", {})) >= 10,
        "big": stats.get("best", 0) >= 10,
        "legend": stats.get("legendary", 0) >= 1,
        "night": stats.get("night", 0) >= 1,
    }
    return [a for a in ACHIEVEMENTS if checks.get(a["id"]) and a["id"] not in already]


# ---------------------------------------------------------
# Сундук рыбака
# ---------------------------------------------------------

CHEST_CHANCE = 0.12
CHEST_ENERGY = 25


def open_chest(rng, reward_percent: int, xp_percent: int) -> dict:
    kind = rng.choice(("coins", "bait", "xp", "energy"))

    if kind == "energy":
        return {"kind": "energy", "amount": CHEST_ENERGY}

    if kind == "coins":
        return {"kind": "coins", "amount": round((200 + rng.randint(0, 600)) * reward_percent / 100)}

    if kind == "bait":
        bait = rng.choice(("maggots", "corn", "bread", "livebait"))
        return {"kind": "bait", "bait": bait, "amount": 2 + rng.randint(0, 4)}

    return {"kind": "xp", "amount": round((80 + rng.randint(0, 120)) * xp_percent / 100)}


def location_by_key(key: str) -> Location | None:
    return next((loc for loc in LOCATIONS if loc.key == key), None)


def location_index(key: str) -> int:
    return next((i for i, loc in enumerate(LOCATIONS) if loc.key == key), 0)
