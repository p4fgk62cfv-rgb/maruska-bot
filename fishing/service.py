"""
Рыбалка — серверная логика.

Сервер решает всё, что влияет на награду: какая рыба клюнула, вес,
трофей, алмазы, опыт, лимиты. Телефон игрока только показывает и
сообщает, вытащил ли он рыбу в мини-игре.

Алмазы — общие с Марой (change_balance, причины «fishing» и
«fishing_shop»), опыт — общий (progress.award). Поэтому рыбалка
видна в экономике, аналитике и истории профиля.

Защита экономики (настройки владельца):
  • reward_percent — алмазы от базовых цен игры (они рассчитаны на
    отдельную экономику до 3000 за рыбу);
  • daily_cap — потолок алмазов с рыбалки в сутки на человека;
  • cooldown — пауза между забросами;
  • min_fight — вытащить рыбу быстрее нельзя (защита от ботов).
"""

import logging
import random
import secrets
from datetime import datetime, timedelta

from sqlalchemy import func, select, update

from database.database import session_scope, utcnow
from database.models import FishingCast, FishingCatch, FishingPlayer, GroupMember, UserProfile

from fishing import rules as R


logger = logging.getLogger("maruska.fishing")

DEFAULT_SETTINGS = {
    "enabled": True,
    "reward_percent": 10,
    "xp_percent": 20,
    "cooldown": 8,
    "daily_cap": 800,
    "min_fight": 2,
    "energy_max": 100,       # запас на 1 уровне; 0 — энергия выключена
    "energy_regen": 2,       # минут на 1 единицу
    "energy_cost": 5,        # цена заброса в Тихой заводи; дальше +1 за водоём
    "refill_price": 120,     # термос чая, алмазов
    "refill_amount": 50,
    "refill_per_day": 3,
}

LIMITS = {
    "reward_percent": (0, 100),
    "xp_percent": (0, 100),
    "cooldown": (0, 300),
    "daily_cap": (0, 100000),
    "min_fight": (0, 30),
    "energy_max": (0, 1000),
    "energy_regen": (1, 60),
    "energy_cost": (1, 100),
    "refill_price": (0, 100000),
    "refill_amount": (1, 1000),
    "refill_per_day": (0, 20),
}

CAST_TTL = 180          # секунд: дольше заброс не живёт
START_BAIT = {"maggots": 5, "corn": 5, "bread": 5, "livebait": 3, "fly": 3, "wobbler": 2, "spinner": 2, "softbait": 2}

_settings: dict = dict(DEFAULT_SETTINGS)


class FishingError(Exception):
    """Понятная игроку причина отказа."""


# ---------------------------------------------------------
# Настройки владельца (общие для всего бота, chat_id = 0)
# ---------------------------------------------------------

def settings() -> dict:
    return dict(_settings)


def clean_settings(data: dict | None) -> dict:
    result = dict(DEFAULT_SETTINGS)

    for key, value in (data or {}).items():
        if key == "enabled":
            result["enabled"] = bool(value)
        elif key in LIMITS:
            low, high = LIMITS[key]
            try:
                result[key] = max(low, min(high, int(value)))
            except (TypeError, ValueError):
                pass

    return result


def prime_settings(data: dict | None) -> None:
    _settings.clear()
    _settings.update(clean_settings(data))


async def reload_settings() -> None:
    from database.repository import get_group_settings

    prime_settings((await get_group_settings(0)).get("fishing_settings"))


async def save_settings(data: dict) -> dict:
    from database.repository import set_group_setting

    cleaned = clean_settings({**_settings, **(data or {})})
    await set_group_setting(chat_id=0, key="fishing_settings", value=cleaned)
    prime_settings(cleaned)
    return cleaned


# ---------------------------------------------------------
# Профиль
# ---------------------------------------------------------

def _today() -> str:
    return utcnow().strftime("%Y-%m-%d")


def _new_player(telegram_id: int) -> FishingPlayer:
    return FishingPlayer(
        telegram_id=telegram_id, rod_levels={"starter": 1}, owned_rods=["starter"],
        owned_reels=["basic"], owned_bobbers=["wood"], owned_boats=["shore"], bait_stock=dict(START_BAIT), species={}, quests=[], achievements=[],
    )


async def _locked_player(session, telegram_id: int) -> FishingPlayer:
    """Строка игрока с блокировкой до конца транзакции — без гонок и двойных списаний."""
    player = (await session.execute(
        select(FishingPlayer).where(FishingPlayer.telegram_id == telegram_id).with_for_update()
    )).scalar_one_or_none()

    if player is None:
        player = _new_player(telegram_id)
        session.add(player)
        await session.flush()

    return player


def _ensure_quests(player: FishingPlayer) -> None:
    day = _today()
    if player.quests_day != day:
        player.quests_day = day
        player.quests = R.daily_quests(day, player.telegram_id)


def _energy(player: FishingPlayer, level: int, now, s: dict) -> tuple[int, int]:
    """Пересчитать энергию на сейчас и сохранить снимок в профиле."""
    cap = R.energy_cap(level, s["energy_max"])

    if player.energy is None or player.energy_at is None:
        player.energy, player.energy_at = cap, now

    player.energy, player.energy_at = R.energy_now(player.energy, player.energy_at, now, cap, s["energy_regen"] * 60)
    return player.energy, cap


def _refills_left(player: FishingPlayer, s: dict) -> int:
    used = (player.refills or 0) if player.refills_day == _today() else 0
    return max(0, s["refill_per_day"] - used)


def _energy_info(player: FishingPlayer, level: int, now, s: dict) -> dict:
    enabled = s["energy_max"] > 0
    if not enabled:
        return {"enabled": False}

    value, cap = _energy(player, level, now, s)
    regen = s["energy_regen"] * 60
    next_in = 0 if value >= cap else max(0, round(regen - (now - player.energy_at).total_seconds()))
    full_in = 0 if value >= cap else next_in + (cap - value - 1) * regen

    return {
        "enabled": True, "value": value, "max": cap, "regen": regen, "next_in": next_in, "full_in": full_in,
        "cost": R.cast_cost(R.location_index(player.location), s["energy_cost"]),
        "costs": {loc.key: R.cast_cost(i, s["energy_cost"]) for i, loc in enumerate(R.LOCATIONS)},
        "refill_price": s["refill_price"], "refill_amount": s["refill_amount"],
        "refills_left": _refills_left(player, s),
    }


async def _mara_profile(telegram_id: int) -> tuple[int, int, int]:
    """Уровень, опыт и алмазы из общего профиля Мары."""
    async with session_scope() as session:
        row = (await session.execute(
            select(UserProfile.level, UserProfile.xp, UserProfile.coins).where(UserProfile.telegram_id == telegram_id)
        )).one_or_none()
    return (int(row[0] or 1), int(row[1] or 0), int(row[2] or 0)) if row else (1, 0, 0)


async def fished_today(telegram_id: int) -> int:
    start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    async with session_scope() as session:
        return int((await session.execute(
            select(func.coalesce(func.sum(FishingCatch.reward), 0)).where(
                FishingCatch.telegram_id == telegram_id, FishingCatch.created_at >= start)
        )).scalar() or 0)


async def profile(telegram_id: int) -> dict:
    level, xp, coins = await _mara_profile(telegram_id)

    async with session_scope() as session:
        player = await _locked_player(session, telegram_id)
        _ensure_quests(player)
        energy = _energy_info(player, level, utcnow(), settings())
        await session.commit()
        data = _player_dict(player)

    data["energy"] = energy
    from progress.xp import progress as xp_progress

    data.update({
        "diamonds": coins,
        "level": level,
        "xp": xp,
        "level_progress": xp_progress(xp)["percent"],
        "fished_today": await fished_today(telegram_id),
        "settings": settings(),
    })
    return data


def _owned(items: list | None, free: str) -> list:
    """Бесплатная катушка и поплавок есть у всех, даже у старых профилей."""
    items = list(items or [])
    return items if free in items else [free] + items


def _player_dict(p: FishingPlayer) -> dict:
    return {
        "location": p.location, "rod": p.rod, "rod_levels": p.rod_levels or {"starter": 1},
        "owned_rods": p.owned_rods or ["starter"],
        "reel": p.reel if p.reel in R.REELS else "basic", "owned_reels": _owned(p.owned_reels, "basic"),
        "bobber": p.bobber if p.bobber in R.BOBBERS else "wood", "owned_bobbers": _owned(p.owned_bobbers, "wood"),
        "catalog": R.catalog(), "boat": p.boat, "owned_boats": p.owned_boats or ["shore"],
        "bait": p.bait, "bait_stock": p.bait_stock or {}, "caught": p.caught, "best": p.best,
        "legendary": p.legendary, "night": p.night, "species": p.species or {},
        "lifetime_weight": round(p.lifetime_weight or 0, 2), "streak": p.streak, "last_day": p.last_day,
        "quests": p.quests or [], "chests": p.chests, "opened_chests": p.opened_chests,
        "achievements": p.achievements or [],
    }


# ---------------------------------------------------------
# Выбор места и снастей
# ---------------------------------------------------------

async def choose_gear(telegram_id: int, location: str | None = None, rod: str | None = None,
                 boat: str | None = None, bait: str | None = None,
                 reel: str | None = None, bobber: str | None = None) -> dict:
    level, _xp, _coins = await _mara_profile(telegram_id)

    async with session_scope() as session:
        player = await _locked_player(session, telegram_id)

        if location is not None:
            loc = R.location_by_key(location)
            if loc is None:
                raise FishingError("Такого водоёма нет")
            if level < loc.level:
                raise FishingError(f"🔒 {loc.name} открывается с {loc.level} уровня")
            player.location = loc.key

        if rod is not None:
            if rod not in (player.owned_rods or []):
                raise FishingError("Эта удочка не куплена")
            player.rod = rod

        if reel is not None:
            if reel not in _owned(player.owned_reels, "basic"):
                raise FishingError("Эта катушка не куплена")
            player.reel = reel

        if bobber is not None:
            if bobber not in _owned(player.owned_bobbers, "wood"):
                raise FishingError("Этот поплавок не куплен")
            player.bobber = bobber

        if boat is not None:
            if boat not in (player.owned_boats or []):
                raise FishingError("Эта лодка не куплена")
            player.boat = boat

        if bait is not None:
            if bait not in R.BAITS:
                raise FishingError("Такой наживки нет")
            player.bait = bait

        await session.commit()

    return await profile(telegram_id)


# ---------------------------------------------------------
# Заброс и поимка
# ---------------------------------------------------------

async def cast(telegram_id: int, chat_id: int | None = None, rng=random) -> dict:
    s = settings()

    if not s["enabled"]:
        raise FishingError("🎣 Рыбалка сейчас выключена")

    level, _xp, _coins = await _mara_profile(telegram_id)
    now = utcnow()

    async with session_scope() as session:
        player = await _locked_player(session, telegram_id)

        if player.last_cast_at and (now - player.last_cast_at).total_seconds() < s["cooldown"]:
            left = s["cooldown"] - int((now - player.last_cast_at).total_seconds())
            raise FishingError(f"⏳ Рыба пугается — подожди {max(left, 1)} сек.")

        location = R.location_by_key(player.location) or R.LOCATIONS[0]

        if level < location.level:
            location = R.LOCATIONS[0]
            player.location = location.key

        # Энергия — до наживки: без сил наживка не тратится
        if s["energy_max"] > 0:
            value, _cap = _energy(player, level, now, s)
            cost = R.cast_cost(R.location_index(location.key), s["energy_cost"])
            if value < cost:
                raise FishingError(f"⚡ Нет сил на заброс: нужно {cost}, есть {value}. "
                                   f"+1 каждые {s['energy_regen']} мин или выпей чаю из термоса")
            player.energy = value - cost

        bait = R.BAITS.get(player.bait) or R.BAITS["worm"]

        # Червь бесплатный и бесконечный — без наживки никто не застрянет
        if not bait.free:
            stock = dict(player.bait_stock or {})
            if stock.get(bait.key, 0) <= 0:
                raise FishingError(f"🪱 Кончилась наживка «{bait.name}» — купи в снаряжении или возьми червя")
            stock[bait.key] -= 1
            player.bait_stock = stock

        rod = R.RODS.get(player.rod) or R.RODS["starter"]
        rod_level = int((player.rod_levels or {}).get(rod.key, 1))
        reel = R.REELS.get(player.reel) or R.REELS["basic"]
        bobber = R.BOBBERS.get(player.bobber) or R.BOBBERS["wood"]
        effective = R.with_reel(rod, rod_level, reel)

        fish = R.choose_fish(location, effective, bait, rng)
        weight, trophy, length = R.roll_catch(fish, rng, R.BASE_TROPHY + bobber.trophy)
        bite_delay = R.bite_delay(bobber, rng)

        cast_id = secrets.token_hex(12)
        session.add(FishingCast(
            id=cast_id, telegram_id=telegram_id, chat_id=chat_id, fish_key=fish.key, weight=weight,
            length=length, trophy=trophy, location=location.key, bait=bait.key, bite_delay=bite_delay,
        ))
        player.last_cast_at = now
        energy = _energy_info(player, level, now, s)
        await session.commit()

    # Игроку заранее видны только вид рыбы и её сила — вес и награда после поимки
    return {"cast_id": cast_id, "fish": fish.key, "power": fish.power, "rarity": fish.rarity,
            "bite_delay": bite_delay, "bait": bait.key, "energy": energy}


async def land(telegram_id: int, cast_id: str, success: bool, display_name: str | None = None, rng=random) -> dict:
    s = settings()
    now = utcnow()

    async with session_scope() as session:
        item = (await session.execute(
            select(FishingCast).where(FishingCast.id == cast_id, FishingCast.telegram_id == telegram_id).with_for_update()
        )).scalar_one_or_none()

        if item is None or item.resolved:
            raise FishingError("Этот заброс уже засчитан")

        elapsed = (now - item.created_at).total_seconds()

        if elapsed > CAST_TTL:
            item.resolved = True
            await session.commit()
            raise FishingError("Рыба давно ушла — забрось заново")

        if success and elapsed < item.bite_delay + s["min_fight"]:
            raise FishingError("Слишком быстро — рыбу так не вытащить")

        item.resolved = True

        if not success:
            await session.commit()
            return {"success": False}

        fish = R.FISH[item.fish_key]
        location = R.location_by_key(item.location) or R.LOCATIONS[0]
        player = await _locked_player(session, telegram_id)
        _ensure_quests(player)

        boat = R.BOATS.get(player.boat) or R.BOATS["shore"]
        reward = R.catch_reward(fish, item.trophy, R.location_index(location.key), boat, s["reward_percent"])
        xp = R.catch_xp(fish, item.trophy, s["xp_percent"])

        # Потолок алмазов с рыбалки в сутки
        already = await fished_today(telegram_id)
        capped = False
        if s["daily_cap"] and already + reward > s["daily_cap"]:
            reward = max(0, s["daily_cap"] - already)
            capped = True

        # Серия дней — за первый улов дня
        day = _today()
        streak_gain = 0
        if player.last_day != day:
            yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
            player.streak = (player.streak or 0) + 1 if player.last_day == yesterday else 1
            player.last_day = day
            streak_gain = R.streak_bonus(player.streak, s["reward_percent"])

        player.caught = (player.caught or 0) + 1
        species = dict(player.species or {})
        species[fish.key] = species.get(fish.key, 0) + 1
        player.species = species
        player.best = max(player.best or 0, item.weight)
        player.lifetime_weight = (player.lifetime_weight or 0) + item.weight

        if fish.rarity in R.LEGEND_RANKS:
            player.legendary = (player.legendary or 0) + 1
        if location.night:
            player.night = (player.night or 0) + 1

        # Задания дня
        quest_reward = 0
        quests = [dict(q) for q in (player.quests or [])]
        finished = []
        for q in quests:
            if q.get("done"):
                continue
            q["progress"] = min(q["target"], q.get("progress", 0) + R.quest_step(q, fish, item.weight, location.night, location))
            if q["progress"] >= q["target"]:
                q["done"] = True
                gain = round(q["reward"] * s["reward_percent"] / 100)
                quest_reward += gain
                finished.append({"title": q["title"], "reward": gain})
        player.quests = quests

        # Достижения рыбалки
        stats = {"caught": player.caught, "species": species, "best": player.best,
                 "legendary": player.legendary, "night": player.night}
        fresh = R.unlocked_achievements(stats, list(player.achievements or []))
        achievement_reward = sum(round(a["reward"] * s["reward_percent"] / 100) for a in fresh)
        player.achievements = list(player.achievements or []) + [a["id"] for a in fresh]

        chest = rng.random() < R.CHEST_CHANCE
        if chest:
            player.chests = (player.chests or 0) + 1

        session.add(FishingCatch(
            telegram_id=telegram_id, chat_id=item.chat_id, fish_key=fish.key, weight=item.weight,
            trophy=item.trophy, reward=reward, xp=xp, location=location.key,
        ))
        chat_id = item.chat_id
        await session.commit()

    from database.repository import change_balance

    total = reward + streak_gain + quest_reward + achievement_reward

    if total:
        await change_balance(telegram_id=telegram_id, amount=total, reason="fishing",
                             note=f"Рыбалка: {fish.name} {item.weight} кг", chat_id=chat_id,
                             display_name=display_name)

    level_up = None
    if xp:
        try:
            from progress.service import award

            result = await award(telegram_id=telegram_id, amount=xp, display_name=display_name,
                                 chat_id=chat_id, with_economy=True)
            level_up = result.get("level") if result and result.get("level_up") else None
        except Exception as error:
            logger.warning("FISHING XP: %s", error)

    return {
        "success": True, "fish": fish.key, "name": fish.name, "rarity": fish.rarity,
        "weight": item.weight, "length": item.length, "trophy": item.trophy,
        "reward": reward, "xp": xp, "capped": capped, "streak_bonus": streak_gain,
        "quests_done": finished, "achievements": [{"name": a["name"], "icon": a["icon"]} for a in fresh],
        "achievement_reward": achievement_reward, "chest": chest, "level_up": level_up,
        "chat_id": chat_id, "total": total,
    }


# ---------------------------------------------------------
# Магазин
# ---------------------------------------------------------

async def _pay(telegram_id: int, cost: int, note: str) -> None:
    from database.repository import change_balance

    if cost <= 0:
        return

    ok, balance = await change_balance(telegram_id=telegram_id, amount=-cost, reason="fishing_shop",
                                       note=note, allow_negative=False)
    if not ok:
        raise FishingError(f"💎 Не хватает алмазов: нужно {cost}, у тебя {balance}")


async def _refund(telegram_id: int, cost: int, note: str) -> None:
    from database.repository import change_balance

    if cost > 0:
        await change_balance(telegram_id=telegram_id, amount=cost, reason="admin", note=f"Возврат: {note}")


async def buy(telegram_id: int, kind: str, key: str) -> dict:
    """
    Покупка: удочка, улучшение удочки, лодка, пачка наживки.
    Сначала проверка, потом списание, потом выдача; если выдать не
    удалось — алмазы возвращаются.
    """
    level, _xp, _coins = await _mara_profile(telegram_id)

    async with session_scope() as session:
        player = await _locked_player(session, telegram_id)

        if kind == "rod":
            rod = R.RODS.get(key)
            if rod is None:
                raise FishingError("Такой удочки нет")
            if key in (player.owned_rods or []):
                player.rod = key
                await session.commit()
                return await profile(telegram_id)
            if level < rod.level:
                raise FishingError(f"🔒 Нужен {rod.level} уровень")
            cost, note = rod.price, f"Удочка «{rod.name}»"

        elif kind in ("reel", "bobber"):
            table, owned_attr, free = (R.REELS, "owned_reels", "basic") if kind == "reel" else (R.BOBBERS, "owned_bobbers", "wood")
            item = table.get(key)
            if item is None:
                raise FishingError("Такой катушки нет" if kind == "reel" else "Такого поплавка нет")
            if key in _owned(getattr(player, owned_attr), free):
                setattr(player, kind, key)
                await session.commit()
                return await profile(telegram_id)
            if level < item.level:
                raise FishingError(f"🔒 Нужен {item.level} уровень")
            cost, note = item.price, ("Катушка «" if kind == "reel" else "Поплавок «") + item.name + "»"

        elif kind == "energy":
            s = settings()
            if s["energy_max"] <= 0:
                raise FishingError("Энергия выключена — пить чай незачем")
            value, cap = _energy(player, level, utcnow(), s)
            if value >= cap:
                raise FishingError("⚡ Сил и так полно")
            if _refills_left(player, s) <= 0:
                raise FishingError(f"☕ Термос пуст: не больше {s['refill_per_day']} раз в день")
            cost, note = s["refill_price"], f"Термос чая +{s['refill_amount']} ⚡"

        elif kind == "upgrade":
            current = int((player.rod_levels or {}).get(player.rod, 1))
            if current >= R.MAX_ROD_LEVEL:
                raise FishingError("🏆 Удочка уже максимального уровня")
            cost, note = R.upgrade_cost(current), f"Улучшение удочки до {current + 1}"

        elif kind == "boat":
            boat = R.BOATS.get(key)
            if boat is None:
                raise FishingError("Такой лодки нет")
            if key in (player.owned_boats or []):
                player.boat = key
                await session.commit()
                return await profile(telegram_id)
            if level < boat.level:
                raise FishingError(f"🔒 Нужен {boat.level} уровень")
            cost, note = boat.price, f"Лодка «{boat.name}»"

        elif kind == "bait":
            bait = R.BAITS.get(key)
            if bait is None or bait.free:
                raise FishingError("Эту наживку не продают")
            cost, note = bait.price * R.BAIT_PACK, f"Наживка «{bait.name}» ×{R.BAIT_PACK}"

        else:
            raise FishingError("Неизвестная покупка")

        await _pay(telegram_id, cost, note)

        try:
            if kind == "rod":
                player.owned_rods = list(player.owned_rods or []) + [key]
                levels = dict(player.rod_levels or {})
                levels.setdefault(key, 1)
                player.rod_levels = levels
                player.rod = key
            elif kind == "energy":
                s = settings()
                player.energy = (player.energy or 0) + s["refill_amount"]
                player.refills = (player.refills or 0) + 1 if player.refills_day == _today() else 1
                player.refills_day = _today()
            elif kind in ("reel", "bobber"):
                attr = "owned_reels" if kind == "reel" else "owned_bobbers"
                setattr(player, attr, _owned(getattr(player, attr), "basic" if kind == "reel" else "wood") + [key])
                setattr(player, kind, key)
            elif kind == "upgrade":
                levels = dict(player.rod_levels or {})
                levels[player.rod] = int(levels.get(player.rod, 1)) + 1
                player.rod_levels = levels
            elif kind == "boat":
                player.owned_boats = list(player.owned_boats or []) + [key]
                player.boat = key
            elif kind == "bait":
                stock = dict(player.bait_stock or {})
                stock[key] = stock.get(key, 0) + R.BAIT_PACK
                player.bait_stock = stock

            await session.commit()
        except Exception:
            await _refund(telegram_id, cost, note)
            raise

    return await profile(telegram_id)


async def open_chest(telegram_id: int, rng=random) -> dict:
    s = settings()

    async with session_scope() as session:
        player = await _locked_player(session, telegram_id)

        if (player.chests or 0) <= 0:
            raise FishingError("🎁 Сундуков пока нет — они выпадают с уловом")

        player.chests -= 1
        player.opened_chests = (player.opened_chests or 0) + 1
        prize = R.open_chest(rng, s["reward_percent"], s["xp_percent"])

        if prize["kind"] == "energy" and s["energy_max"] > 0:
            level, _xp, _coins = await _mara_profile(telegram_id)
            _energy(player, level, utcnow(), s)
            player.energy += prize["amount"]
        elif prize["kind"] == "energy":
            prize = {"kind": "xp", "amount": round(80 * s["xp_percent"] / 100)}

        if prize["kind"] == "bait":
            stock = dict(player.bait_stock or {})
            stock[prize["bait"]] = stock.get(prize["bait"], 0) + prize["amount"]
            player.bait_stock = stock
            prize["name"] = R.BAITS[prize["bait"]].name

        await session.commit()

    if prize["kind"] == "coins" and prize["amount"]:
        from database.repository import change_balance

        await change_balance(telegram_id=telegram_id, amount=prize["amount"], reason="fishing", note="Сундук рыбака")

    if prize["kind"] == "xp" and prize["amount"]:
        from progress.service import award

        await award(telegram_id=telegram_id, amount=prize["amount"])

    return {"prize": prize, "profile": await profile(telegram_id)}


# ---------------------------------------------------------
# Топы и статистика
# ---------------------------------------------------------

async def _names(ids: set[int], chat_id: int | None = None) -> dict:
    if not ids:
        return {}
    async with session_scope() as session:
        stmt = select(GroupMember.telegram_id, GroupMember.display_name).where(GroupMember.telegram_id.in_(ids))
        if chat_id:
            stmt = stmt.where(GroupMember.chat_id == chat_id)
        names = dict((await session.execute(stmt)).all())
        missing = ids - set(names)
        if missing:
            names.update(dict((await session.execute(
                select(UserProfile.telegram_id, UserProfile.display_name).where(UserProfile.telegram_id.in_(missing))
            )).all()))
    return names


async def leaderboard(chat_id: int | None = None, limit: int = 10) -> list[dict]:
    """Лучшие рыбаки: по самому тяжёлому улову, затем по числу рыб. Для группы — только её участники."""
    async with session_scope() as session:
        stmt = select(
            FishingCatch.telegram_id,
            func.max(FishingCatch.weight).label("best"),
            func.count(FishingCatch.id).label("catches"),
        ).group_by(FishingCatch.telegram_id)

        if chat_id:
            members = select(GroupMember.telegram_id).where(GroupMember.chat_id == chat_id)
            stmt = stmt.where(FishingCatch.telegram_id.in_(members))

        rows = (await session.execute(stmt.order_by(func.max(FishingCatch.weight).desc(), func.count(FishingCatch.id).desc()).limit(limit))).all()

    names = await _names({r[0] for r in rows}, chat_id)
    return [{"telegram_id": uid, "name": names.get(uid) or "Рыбак", "best": round(float(best or 0), 2),
             "catches": int(n)} for uid, best, n in rows]


async def admin_stats() -> dict:
    start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    async with session_scope() as session:
        today = (await session.execute(
            select(func.count(FishingCatch.id), func.coalesce(func.sum(FishingCatch.reward), 0),
                   func.count(func.distinct(FishingCatch.telegram_id)))
            .where(FishingCatch.created_at >= start)
        )).one()
        players = (await session.execute(select(func.count(FishingPlayer.telegram_id)))).scalar() or 0
        total = (await session.execute(select(func.count(FishingCatch.id)))).scalar() or 0

        records = (await session.execute(
            select(FishingCatch.fish_key, func.max(FishingCatch.weight), func.count(FishingCatch.id))
            .group_by(FishingCatch.fish_key)
        )).all()

        recent = (await session.execute(
            select(FishingCatch).order_by(FishingCatch.created_at.desc()).limit(15)
        )).scalars().all()

    names = await _names({r.telegram_id for r in recent})

    return {
        "today": {"catches": int(today[0]), "diamonds": int(today[1]), "anglers": int(today[2])},
        "players": int(players),
        "total_catches": int(total),
        "records": sorted(
            [{"fish": k, "name": R.FISH[k].name if k in R.FISH else k, "rarity": R.FISH[k].rarity if k in R.FISH else "",
              "best": round(float(w or 0), 2), "count": int(n)} for k, w, n in records],
            key=lambda r: -r["count"]),
        "recent": [{"name": names.get(r.telegram_id) or "Рыбак", "fish": R.FISH[r.fish_key].name if r.fish_key in R.FISH else r.fish_key,
                    "weight": r.weight, "trophy": r.trophy, "reward": r.reward, "at": r.created_at.isoformat()}
                   for r in recent],
        "top": await leaderboard(None, 10),
        "chances": {
            loc.key: {"name": loc.name, "level": loc.level,
                      "fish": [{"name": R.FISH[k].name, "rarity": R.FISH[k].rarity, "chance": v}
                               for k, v in sorted(R.chances(loc, R.RODS["starter"], R.BAITS["worm"]).items(), key=lambda kv: -kv[1])]}
            for loc in R.LOCATIONS
        },
        "settings": settings(),
    }


# ---------------------------------------------------------
# Объявление крупного улова в группе
# ---------------------------------------------------------

ANNOUNCE_RANKS = ("Легендарная", "Мифическая")


def announcement(result: dict, name: str) -> str | None:
    """
    Текст для группы о крупном улове — или None, если объявлять не нужно:
    не из группы, обычная рыба или группа выключила объявления.
    """
    from html import escape

    from settings.store import is_enabled

    chat_id = result.get("chat_id")

    if not result.get("success") or not chat_id:
        return None

    if not (result.get("trophy") or result.get("rarity") in ANNOUNCE_RANKS):
        return None

    if not is_enabled(chat_id, "fishing_announce"):
        return None

    if result.get("trophy"):
        mark = "👑 трофейного"
    elif result.get("rarity") == "Мифическая":
        mark = "🌟 мифического"
    else:
        mark = "✨ легендарного"

    return (f"🎣 <b>{escape(name)}</b> вытащил(а) {mark} улова: "
            f"<b>{escape(R.FISH[result['fish']].name.lower())}</b> — {result['weight']} кг! 🎉")
