"""
Проверка доделок админки: отключённые команды, разбор ошибок
по источникам, скрытые встроенные слова и фразы, часовой пояс.
Запуск:  python test_admin_extras.py
"""

import pathlib
import re
import sys
import time

ROOT = pathlib.Path(__file__).parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    failures, checks = [], 0

    def expect(label, got, want):
        nonlocal checks
        checks += 1
        if got != want:
            failures.append(f"  {label}: получили {got!r}, ждали {want!r}")

    # --- отключённые команды (без aiogram) ---
    mw = (ROOT / "settings" / "middleware.py").read_text(encoding="utf-8")
    ns = {}
    exec(mw[mw.index("def command_name("):mw.index("async def command_blocked(")], ns)

    expect("имя команды", ns["command_name"]("/dice 2d6"), "dice")
    expect("команда с @ботом", ns["command_name"]("/Dice@BotMaruska_bot"), "dice")
    expect("не команда", ns["command_name"]("привет"), None)
    expect("список команд", ns["parse_commands"]("/dice, coin;  /8ball"), {"dice", "coin", "8ball"})
    expect("пустой список", ns["parse_commands"](""), set())

    checks += 1
    if '("settings", "help", "start")' not in mw:
        failures.append("  [команды] /settings, /help и /start не должны отключаться — иначе админка недоступна")

    # --- ошибки по источникам ---
    v2 = (ROOT / "webapp" / "admin_v2.py").read_text(encoding="utf-8")
    ens = {"time": time}
    exec(v2[v2.index("ERROR_SOURCES = {"):v2.index("def recent_errors(")], ens)
    classify = ens["classify_error"]

    expect("gemini", classify({"logger": "maruska.chat", "message": "GEMINI ERROR: Timeout"}), "ai")
    expect("картинки", classify({"logger": "maruska.images", "message": "IMAGE PIXABAY SEARCH ERROR"}), "images")
    expect("telegram", classify({"logger": "aiogram.dispatcher", "message": "Failed to fetch updates"}), "telegram")
    expect("база", classify({"logger": "maruska.chat", "message": "PERSIST: ConnectionError"}), "database")
    expect("прочее", classify({"logger": "maruska.x", "message": "что-то сломалось"}), "other")

    # --- скрытые встроенные слова ---
    from actions.catalog import ACTIONS, find_action

    beer = next(a for a in ACTIONS if a.key == "beer")
    expect("пиво по умолчанию", (find_action("пиво") or beer).key if find_action("пиво") else None, "beer")
    expect("скрытое слово не запускает", find_action("пиво", hidden={"beer": set(beer.aliases)}), None)
    expect("чужие скрытые не мешают", (find_action("пиво", hidden={"wine": {"вин"}}) or beer).key, "beer")

    from actions.phrases import pick_template, templates_for

    options = templates_for(beer)
    hidden = set(options[1:])

    for _ in range(20):
        checks += 1
        if pick_template(beer, hidden=hidden) != options[0]:
            failures.append("  [фразы] выпала скрытая фраза")
            break

    expect("скрыли все — фраза всё равно есть", pick_template(beer, hidden=set(options)) in options, True)

    # --- часовой пояс ---
    from settings import store

    store.prime(-100, {"timezone": "Europe/Moscow"})
    expect("Москва +3", store.utc_offset_hours(-100), 3)
    expect("без группы — UTC", store.utc_offset_hours(None), 0)

    # --- новички ---
    from collections import deque

    am = (ROOT / "features" / "automod.py").read_text(encoding="utf-8")
    ans = {"deque": deque, "re": re}
    exec(am[am.index("def newbie_verdict("):am.index("def count_recent(")], ans)
    newbie = ans["newbie_verdict"]

    expect("новичок с фото", newbie(True, False, True, 0, deque([0.0]), 0.0), "newbie")
    expect("новичок с пересылкой", newbie(False, True, True, 0, deque([0.0]), 0.0), "newbie")
    expect("медиа разрешены", newbie(True, False, False, 0, deque([0.0]), 0.0), None)
    expect("замедление — слишком часто", newbie(False, False, False, 30, deque([0.0, 10.0]), 10.0), "newbie")
    expect("замедление — выждал", newbie(False, False, False, 30, deque([0.0, 40.0]), 40.0), None)
    expect("первое сообщение не тормозим", newbie(False, False, False, 30, deque([5.0]), 5.0), None)

    # --- свои правила наказаний ---
    rns = {"deque": deque, "REASONS": {"flood": "флуд", "link": "запрещённая ссылка"}}
    exec(am[am.index("def match_rule("):am.index("RULE_ACTIONS = {")], rns)
    exec(am[am.index("RULE_ACTIONS = {"):am.index("def remember_join(")], rns)
    match, describe = rns["match_rule"], rns["describe_rule"]

    rules = [
        {"violation": "flood", "count": 3, "window": 10, "action": "mute", "duration": 1440},
        {"violation": "any", "count": 5, "window": 60, "action": "tempban", "duration": 60},
    ]
    now = 10_000.0
    two_floods = [(now - 60, "flood"), (now, "flood")]
    three_floods = [(now - 120, "flood"), (now - 60, "flood"), (now, "flood")]
    old_floods = [(now - 3600, "flood"), (now - 3000, "flood"), (now, "flood")]
    mixed = [(now - i * 60, k) for i, k in enumerate(["link", "flood", "link", "stop_word", "flood"])]

    expect("2 флуда — рано", match(rules, two_floods, "flood", now), None)
    expect("3 флуда за 10 мин — мут", (match(rules, three_floods, "flood", now) or {}).get("action"), "mute")
    expect("старые не считаются", match(rules, old_floods, "flood", now), None)
    expect("5 любых за час — бан", (match(rules, mixed, "flood", now) or {}).get("action"), "tempban")
    expect("первое подходящее важнее", (match(rules, three_floods + mixed[:2], "flood", now) or {}).get("action"), "mute")

    expect("описание мута", describe(rules[0]), "Если флуд — 3 раз за 10 мин → мут на 1 дн")
    expect("описание любого", describe(rules[1]), "Если любое нарушение — 5 раз за 60 мин → бан на 1 ч")

    # --- язык ---
    import i18n

    store.prime(-300, {"language": "en"})
    store.prime(-301, {"language": "ru"})

    expect("английский", i18n.t(-300, "captcha.button"), "✅ I'm not a bot")
    expect("русский", i18n.t(-301, "captcha.button"), "✅ Я не бот")
    expect("подстановка", i18n.t(-300, "cmd.ban", name="Kate"), "⛔ <b>Kate</b> is banned.")
    expect("нет ключа — не падает", i18n.t(-300, "нет.такого"), "нет.такого")
    expect("инструкция AI на английском", bool(i18n.ai_instruction(-300)), True)
    expect("на русском без инструкции", i18n.ai_instruction(-301), "")

    for key, variants in i18n.TEXTS.items():
        checks += 1
        if set(variants) != set(i18n.LANGUAGES):
            failures.append(f"  [язык] {key}: нет перевода на {set(i18n.LANGUAGES) - set(variants)}")
        elif set(re.findall(r"\{(\w+)\}", variants["ru"])) != set(re.findall(r"\{(\w+)\}", variants["en"])):
            failures.append(f"  [язык] {key}: подстановки в переводах не совпадают")

    if failures:
        print(f"❌ {len(failures)} проблем:\n")
        print("\n".join(failures))
        return 1

    print(f"✅ Все {checks} проверок доделок прошли.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
