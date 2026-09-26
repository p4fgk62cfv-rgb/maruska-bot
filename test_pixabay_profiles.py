"""
Проверка поиска Pixabay: ручные профили владельца и торт без кексов.
Запуск:  python test_pixabay_profiles.py
"""

import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).parent
sys.path.insert(0, str(ROOT))

# Сеть и база не нужны — только логика профилей
sys.modules.setdefault("httpx", types.ModuleType("httpx"))
repo = types.ModuleType("database.repository")
repo.__getattr__ = lambda name: (lambda *a, **k: None)
sys.modules.setdefault("database", types.ModuleType("database"))
sys.modules["database.repository"] = repo

from actions import service as svc  # noqa: E402
from actions.catalog import ACTION_BY_KEY  # noqa: E402
from actions.providers import matches_tags as tags_match  # noqa: E402


def main() -> int:
    failures, checks = [], 0

    def expect(label, got, want):
        nonlocal checks
        checks += 1
        if got != want:
            failures.append(f"  {label}: получили {got!r}, ждали {want!r}")

    cake = ACTION_BY_KEY["cake"]

    # --- торт по умолчанию: кексы и маффины не проходят ---
    query, required, excluded, filters = svc.pixabay_profile(cake, "neutral")
    groups = filters["required_groups"]

    def passes(tags):
        return tags_match(tags, required, excluded, groups)

    expect("настоящий торт", passes("cake, birthday, dessert, layer"), True)
    expect("маффин с тегом cake", passes("muffin, cake, baking"), False)
    expect("капкейк", passes("cupcake, cake, sweet"), False)
    expect("печенье", passes("cookie, cake, sweet"), False)

    # --- слово целиком, а не кусок текста ---
    expect("панкейк не торт", passes("pancake, breakfast, raspberry"), False)
    expect("блины не торт", passes("pancakes, crepes, breakfast"), False)
    expect("чизкейк не торт", passes("cheesecake, dessert"), False)
    expect("торт во множественном", passes("cakes, dessert, sweet"), True)
    expect("торт во фразе", passes("birthday cake, candles"), True)

    from actions.providers import tag_has_word

    for tags, term, want in [
        ("woman, portrait", "man", False), ("mango, fruit", "man", False), ("man, beard", "man", True),
        ("catering, food", "cat", False), ("education", "cat", False), ("cat, kitten", "cat", True),
        ("steak, grill", "tea", False), ("green tea, cup", "tea", True), ("ginger, root", "gin", False),
        ("piece, puzzle", "pie", False), ("apple pie", "pie", True), ("dogs, park", "dog", True),
        ("glasses, wine", "glass", True), ("season, autumn", "sea", False), ("sea, waves", "sea", True),
    ]:
        expect(f"«{term}» в «{tags}»", tag_has_word(tags, term), want)

    before = svc.rules_version(cake, "neutral")

    # --- разбор полей из панели ---
    expect("слова", svc.parse_words("Muffin, cupcake ;cookie"), ["muffin", "cupcake", "cookie"])
    expect("группы", svc.parse_groups("cake, cakes; slice, dessert"), [["cake", "cakes"], ["slice", "dessert"]])
    expect("пусто", svc.parse_groups(""), [])

    # --- ручной профиль владельца ---
    svc.set_pixabay_overrides({"cake": {
        "query": "layered birthday cake slice",
        "required": [["cake"], ["slice", "layer"]],
        "excluded": ["pie"],
    }})

    query, required, excluded, filters = svc.pixabay_profile(cake, "neutral")
    groups = filters["required_groups"]

    expect("свой запрос", query, "layered birthday cake slice")
    expect("свои обязательные", groups, (("cake",), ("slice", "layer")))
    expect("свой запрет добавлен", "pie" in excluded, True)
    expect("встроенные запреты остались", "muffin" in excluded, True)
    expect("оба условия выполнены", tags_match("cake, slice, cream", required, excluded, groups), True)
    expect("нет второго условия", tags_match("cake, cream", required, excluded, groups), False)

    after = svc.rules_version(cake, "neutral")
    expect("отпечаток сменился — коллекция соберётся заново", before != after, True)

    other = ACTION_BY_KEY["beer"]
    expect("другие действия не задеты", svc.get_search_query(other, "neutral") != "layered birthday cake slice", True)

    svc.set_pixabay_overrides({})
    expect("сброс — снова стандартный", svc.rules_version(cake, "neutral"), before)

    if failures:
        print(f"❌ {len(failures)} проблем:\n")
        print("\n".join(failures))
        return 1

    print(f"✅ Все {checks} проверок поиска Pixabay прошли.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
