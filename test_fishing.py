"""
Проверка рыбалки: правила, экономика, настройки, связь с группой.
Запуск:  python test_fishing.py
"""

import pathlib
import random
import re
import sys
import types
from html import escape

ROOT = pathlib.Path(__file__).parent
sys.path.insert(0, str(ROOT))

from fishing import rules as R  # noqa: E402


def main() -> int:
    failures, checks = [], 0

    def expect(label, got, want):
        nonlocal checks
        checks += 1
        if got != want:
            failures.append(f"  {label}: получили {got!r}, ждали {want!r}")

    worm, wobbler, starter = R.BAITS["worm"], R.BAITS["wobbler"], R.RODS["starter"]

    # --- редкость работает ---
    for loc in R.LOCATIONS:
        c = R.chances(loc, starter, worm)
        expect(f"{loc.name}: шансы в сумме 100%", round(sum(c.values())), 100)

    mountain = R.location_by_key("mountain")
    taimen = R.chances(mountain, starter, worm)["taimen"]
    expect("таймень на горном озере редкий (было 33%)", taimen < 5, True)
    expect("воблер поднимает тайменя", R.chances(mountain, starter, wobbler)["taimen"] > taimen, True)

    quiet = R.location_by_key("quiet")
    expect("воблер поднимает щуку", R.chances(quiet, starter, wobbler)["pike"] > R.chances(quiet, starter, worm)["pike"], True)
    expect("сильная удочка чуть поднимает редких",
           R.chances(quiet, R.RODS["premium"], worm)["pike"] > R.chances(quiet, starter, worm)["pike"], True)

    rng = random.Random(7)
    counts = {}
    for _ in range(4000):
        f = R.choose_fish(mountain, starter, worm, rng)
        counts[f.key] = counts.get(f.key, 0) + 1
    expect("розыгрыш совпадает с шансами (окунь чаще всех)", max(counts, key=counts.get), "perch")
    expect("мифической белуги нет вне глубокой воды", "beluga" in quiet.fish, False)

    # --- вес и трофей ---
    for _ in range(300):
        fish = R.FISH["catfish"]
        w, trophy, length = R.roll_catch(fish, rng)
        checks += 1
        if not (fish.min_w <= w <= fish.max_w) or length <= 0:
            failures.append(f"  вес вне диапазона: {w}")
            break
    no_trophy = all(not R.roll_catch(R.FISH["perch"], rng)[1] for _ in range(300))
    expect("у окуня трофеев не бывает", no_trophy, True)

    # --- экономика ---
    shore = R.BOATS["shore"]
    expect("белуга за 10%", R.catch_reward(R.FISH["beluga"], False, 4, shore, 10), 396)
    expect("окунь за 10%", R.catch_reward(R.FISH["perch"], False, 0, shore, 10), 9)
    expect("трофей ×2.4", R.catch_reward(R.FISH["pike"], True, 0, shore, 10), 77)
    expect("лодка даёт бонус", R.catch_reward(R.FISH["pike"], False, 0, R.BOATS["legend"], 10) > R.catch_reward(R.FISH["pike"], False, 0, shore, 10), True)
    expect("0% — без алмазов", R.catch_reward(R.FISH["beluga"], True, 4, shore, 0), 0)
    expect("серия не растёт после недели", R.streak_bonus(30, 10), R.streak_bonus(7, 10))
    expect("улучшение удочки дорожает", R.upgrade_cost(3) > R.upgrade_cost(1), True)
    expect("червь бесплатный", (R.BAITS["worm"].free, R.BAITS["worm"].price), (True, 0))

    # --- задания и достижения ---
    q1, q2 = R.daily_quests("2026-09-26", 1), R.daily_quests("2026-09-26", 1)
    expect("задания дня стабильны", [q["id"] for q in q1], [q["id"] for q in q2])
    expect("три задания", len(q1), 3)
    expect("у разных игроков бывают разные", any(
        [q["id"] for q in R.daily_quests("2026-09-26", 1)] != [q["id"] for q in R.daily_quests("2026-09-26", u)] for u in range(2, 30)), True)

    river = R.location_by_key("river")
    expect("ночь засчитывается только ночью", R.quest_step({"type": "night"}, R.FISH["pike"], 1, False, quiet), 0)
    expect("речное задание на реке", R.quest_step({"type": "river"}, R.FISH["bream"], 1, False, river), 1)
    expect("тяжёлый трофей от 4 кг", R.quest_step({"type": "weight"}, R.FISH["carp"], 4.0, False, quiet), 1)

    got = [a["id"] for a in R.unlocked_achievements({"caught": 1, "species": {"pike": 1}, "best": 2, "legendary": 0, "night": 0}, [])]
    expect("первая рыба", got, ["first"])
    expect("не выдаётся повторно", R.unlocked_achievements({"caught": 1}, ["first"]), [])

    # --- настройки владельца: границы ---
    sys.modules.setdefault("sqlalchemy", types.ModuleType("sqlalchemy"))
    src = (ROOT / "fishing" / "service.py").read_text(encoding="utf-8")
    ns = {}
    exec(src[src.index("DEFAULT_SETTINGS = "):src.index("CAST_TTL")], ns)
    exec(src[src.index("def clean_settings("):src.index("def prime_settings(")], ns)
    clean = ns["clean_settings"]
    expect("процент не больше 100", clean({"reward_percent": 900})["reward_percent"], 100)
    expect("отрицательное — ноль", clean({"cooldown": -5})["cooldown"], 0)
    expect("мусор игнорируется", clean({"daily_cap": "abc"})["daily_cap"], 800)
    expect("неизвестные ключи отбрасываются", "hack" in clean({"hack": 1}), False)

    for bad in ("_marа_profile", "async def select("):
        expect(f"в сервисе нет «{bad}»", bad in src, False)

    # --- катушки и поплавки ---
    expect("стартовая катушка бесплатная и без бонуса",
           (R.REELS["basic"].price, R.REELS["basic"].control, R.REELS["basic"].power), (0, 0, 0))
    expect("деревянный поплавок бесплатный", (R.BOBBERS["wood"].price, R.BOBBERS["wood"].sense), (0, 0.0))
    reels, bobbers = list(R.REELS.values()), list(R.BOBBERS.values())
    expect("катушки дорожают и усиливаются",
           all(b.price > a.price and b.control >= a.control and b.power >= a.power for a, b in zip(reels, reels[1:])), True)
    expect("поплавки дорожают и чувствительнее",
           all(b.price > a.price and b.sense > a.sense for a, b in zip(bobbers, bobbers[1:])), True)
    expect("поклёвка не мгновенная даже с лучшим поплавком", max(b.sense for b in bobbers) < .5, True)

    carp = R.RODS["carp"]
    boosted = R.with_reel(carp, 2, R.REELS["gold"])
    expect("катушка и прокачка складываются с удочкой",
           (boosted.control, boosted.power), (carp.control + 3 + 15, carp.power + 4 + 18))
    expect("стартовая катушка удочку не меняет", R.with_reel(carp, 1, R.REELS["basic"]), carp)

    river = R.location_by_key("river")
    expect("сильная катушка поднимает шанс сома",
           R.chances(river, boosted, worm)["catfish"] > R.chances(river, carp, worm)["catfish"], True)

    slow = [R.bite_delay(R.BOBBERS["wood"], random.Random(i)) for i in range(50)]
    fast = [R.bite_delay(R.BOBBERS["crystal"], random.Random(i)) for i in range(50)]
    expect("кристальный поплавок быстрее деревянного", all(f < s for f, s in zip(fast, slow)), True)
    expect("задержка поклёвки положительная", min(fast) > 0, True)

    cat = R.catalog()
    expect("в каталоге все катушки", [r["key"] for r in cat["reels"]], list(R.REELS))
    expect("в каталоге все поплавки", [b["key"] for b in cat["bobbers"]], list(R.BOBBERS))
    for k in R.REELS:
        expect(f"есть картинка катушки {k}", (ROOT / f"webapp/static/fishing/assets/fishing/gear/reel_{k}.png").exists(), True)
    for k in R.BOBBERS:
        expect(f"есть картинка поплавка {k}", (ROOT / f"webapp/static/fishing/assets/fishing/gear/float_{k}.png").exists(), True)

    boats = list(R.BOATS.values())
    expect("во флоте 9 лодок", len(boats), 9)
    expect("старые ключи лодок сохранены (купленное не пропадает)",
           {"shore", "boat", "speedboat", "legend"} <= set(R.BOATS), True)
    expect("стартовая лодка бесплатная и без бонуса", (R.BOATS["shore"].price, R.BOATS["shore"].reward), (0, 0.0))
    expect("лодки дорожают и дают больше",
           all(b.price > a.price and b.reward > a.reward and b.control > a.control for a, b in zip(boats, boats[1:])), True)
    expect("в каталоге все лодки", [b["key"] for b in R.catalog()["boats"]], list(R.BOATS))
    for k in R.BOATS:
        expect(f"есть картинка лодки {k}", (ROOT / f"webapp/static/fishing/assets/fishing/boats/{k}.png").exists(), True)
    expect("дракон даёт больше награды, чем берег",
           R.catch_reward(R.FISH["carp"], False, 0, R.BOATS["dragon"], 100) > R.catch_reward(R.FISH["carp"], False, 0, R.BOATS["shore"], 100), True)

    # --- энергия ---
    from datetime import datetime, timedelta
    t0 = datetime(2026, 1, 1, 12, 0, 0)
    expect("запас на 1 уровне равен базе", R.energy_cap(1, 100), 100)
    expect("запас растёт с уровнем", R.energy_cap(11, 100), 120)
    expect("запас не больше полутора баз", R.energy_cap(99, 100), 150)
    expect("цена заброса растёт с водоёмом", [R.cast_cost(i, 5) for i in range(5)], [5, 6, 7, 8, 9])
    expect("за 10 минут +5 при 2 мин/ед.", R.energy_now(10, t0, t0 + timedelta(minutes=10), 100, 120)[0], 15)
    expect("неполная минута не теряется",
           R.energy_now(10, t0, t0 + timedelta(minutes=3), 100, 120)[1], t0 + timedelta(minutes=2))
    expect("выше запаса не восстанавливается", R.energy_now(95, t0, t0 + timedelta(hours=5), 100, 120)[0], 100)
    expect("термос над запасом не срезается", R.energy_now(130, t0, t0 + timedelta(hours=5), 100, 120)[0], 130)
    expect("энергия выключается нулём", clean({"energy_max": 0})["energy_max"], 0)
    expect("регенерация не быстрее минуты", clean({"energy_regen": 0})["energy_regen"], 1)
    expect("сервис проверяет энергию до наживки", src.index("Нет сил на заброс") < src.index("Кончилась наживка"), True)
    expect("термос продаётся", 'kind == "energy"' in src, True)
    expect("сундук может дать энергию", "energy" in R.open_chest.__code__.co_consts, True)

    expect("сервис учитывает катушку при забросе", "R.with_reel(rod, rod_level, reel)" in src, True)
    expect("сервис продаёт катушки и поплавки", 'kind in ("reel", "bobber")' in src, True)

    # --- ссылка из группы ---
    api = (ROOT / "webapp" / "fishing_api.py").read_text(encoding="utf-8")
    ns2 = {}
    exec(api[api.index("def parse_start_param("):api.index("def _player(")], ns2)
    parse = ns2["parse_start_param"]
    expect("группа из ссылки", parse("g1001234567890"), -1001234567890)
    for bad in (None, "", "g", "g12x", "1001", "gabc"):
        expect(f"мусор «{bad}» — не группа", parse(bad), None)

    expect("клиент не может записать себе состояние", "add_put(" in api, False)
    expect("клиент не присылает улов", "/api/fishing/catch" in api, False)

    game = (ROOT / "games" / "fishing.py").read_text(encoding="utf-8")
    ns3 = {"re": re, "escape": escape}
    exec(game[game.index("OPEN_WORDS = "):game.index("async def open_fishing(")], ns3)
    ns3["Message"] = object
    exec(game[game.index("def is_open_request("):game.index("@router.message(is_open_request)")], ns3)
    expect("ссылка на группу", ns3["start_param"](-1001234567890), "g1001234567890")
    expect("круговая проверка ссылки", parse(ns3["start_param"](-1001234567890)), -1001234567890)
    expect("«топ рыбаков»", ns3["TOP_RE"].match("топ рыбаков") is not None, True)
    top = ns3["format_top"]([{"name": "<b>Стас</b>", "best": 18.4, "catches": 40}])
    expect("топ: медаль и экранирование", "🥇 <b>&lt;b&gt;Стас&lt;/b&gt;</b>" in top, True)

    class Msg:
        def __init__(self, text, reply=None):
            self.text, self.reply_to_message = text, reply

    expect("«рыбалка» — открыть игру", ns3["is_open_request"](Msg("Рыбалка")), True)
    expect("«рыбалка» в ответ — это действие, не игра", ns3["is_open_request"](Msg("рыбалка", reply=object())), False)

    # --- объявление крупного улова ---
    from settings import store

    fsrc = (ROOT / "fishing" / "service.py").read_text(encoding="utf-8")
    ns4 = {"R": R}
    exec(fsrc[fsrc.index("ANNOUNCE_RANKS = "):], ns4)
    ann = ns4["announcement"]
    store.prime(-700, {})
    big = {"success": True, "chat_id": -700, "trophy": True, "rarity": "Легендарная", "fish": "catfish", "weight": 18.4}
    expect("трофей объявляется", "трофейного" in (ann(big, "<b>Стас</b>") or ""), True)
    expect("имя экранируется", "&lt;b&gt;Стас" in (ann(big, "<b>Стас</b>") or ""), True)
    expect("обычная рыба — тихо", ann({**big, "trophy": False, "rarity": "Обычная"}, "x"), None)
    expect("не из группы — тихо", ann({**big, "chat_id": None}, "x"), None)
    store.prime(-701, {"fishing_announce": False})
    expect("группа выключила объявления", ann({**big, "chat_id": -701}, "x"), None)

    # --- клиент: мост к серверу подключён ---
    page = (ROOT / "webapp" / "static" / "fishing" / "index.html").read_text(encoding="utf-8")
    expect("мост подключён после app.js", page.index("server.js") > page.index("app.js"), True)

    if failures:
        print(f"❌ {len(failures)} проблем:\n")
        print("\n".join(failures))
        return 1

    print(f"✅ Все {checks} проверок рыбалки прошли.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
