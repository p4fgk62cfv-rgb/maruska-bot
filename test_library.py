"""
Проверка своей коллекции картинок: хэштеги, названия, авто-привязка.
Запуск:  python test_library.py
"""

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).parent
sys.path.insert(0, str(ROOT))

src = (ROOT / "library_core.py").read_text(encoding="utf-8")
ns = {"re": re}
exec(src[src.index("CATS = \"cats\""):src.index("# ---------------------------------------------------------\n# Чистые функции")], ns)
exec(src[src.index("def normalize_tag("):src.index("# ---------------------------------------------------------\n# Привязки")], ns)


def main() -> int:
    failures, checks = [], 0

    def expect(label, got, want):
        nonlocal checks
        checks += 1
        if got != want:
            failures.append(f"  {label}: получили {got!r}, ждали {want!r}")

    tag_from_caption, normalize, guess = ns["tag_from_caption"], ns["normalize_tag"], ns["guess_target"]

    expect("хэштег в подписи", tag_from_caption("#пиво"), "пиво")
    expect("хэштег среди текста", tag_from_caption("вот холодное #Пиво 🍺"), "пиво")
    expect("первый из нескольких", tag_from_caption("#кошки #милые"), "кошки")
    expect("подчёркивание → пробел", tag_from_caption("#мои_котики"), "мои котики")
    expect("ё → е", tag_from_caption("#Ёлки"), "елки")
    expect("без хэштега", tag_from_caption("просто фото"), None)
    expect("пустая подпись", tag_from_caption(None), None)
    expect("мусор отбрасывается", normalize("#!!!"), None)
    expect("длина ограничена", len(normalize("#" + "а" * 100)), 40)

    expect("кошки → котики", guess("кошки"), "cats")
    expect("котики → котики", guess("котики"), "cats")
    expect("пиво → действие", guess("пиво"), "beer")
    expect("незнакомое — без привязки", guess("абракадабра"), None)

    # --- память хэштега для серии альбомов ---
    resolve = ns["resolve_tag"]

    expect("своя подпись важнее", resolve("вино", ("пиво", 100.0), 110.0), "вино")
    expect("без подписи сразу следом — тот же тег", resolve(None, ("пиво", 100.0), 110.0), "пиво")
    expect("через 2 минуты ещё помним", resolve(None, ("пиво", 100.0), 220.0), "пиво")
    expect("позже — уже не помним", resolve(None, ("пиво", 100.0), 221.0), None)
    expect("никогда не было тега", resolve(None, None, 5.0), None)

    # --- коллекция как своё действие ---
    import library_core as lib
    from types import SimpleNamespace
    from actions import custom as ac
    from actions.phrases import templates_for

    expect("основа слова", lib.stem("булочка"), "булочк")
    expect("короткое не режем", lib.stem("кот"), "кот")

    for text, want in [("булочка", True), ("Булочку!", True), ("булочки", True), ("булочкой", True),
                       ("@kate булочку", True), ("булочка с маком", True),
                       ("я вчера ела очень вкусную булочку", False), ("булка", False), ("", False)]:
        expect(f"триггер «{text}»", lib.trigger_matches(text, ["булочка"]), want)

    lib.prime_collections([
        SimpleNamespace(tag="булочка", emoji="🥐", as_action=True, triggers=["плюшка"], phrase=None),
        SimpleNamespace(tag="выключенная", emoji="✨", as_action=False, triggers=[], phrase=None),
        SimpleNamespace(tag="пончик", emoji="🍩", as_action=True, triggers=[], phrase="{emoji} {actor} и {target}: {item}"),
    ])

    found = lib.find_collection_action("булочку")
    expect("своё действие найдено", found.key if found else None, "lib:булочка")
    expect("эмодзи коллекции", found.emoji if found else None, "🥐")
    expect("доп. слово-триггер", (lib.find_collection_action("плюшку") or SimpleNamespace(key=None)).key, "lib:булочка")
    expect("выключенная не срабатывает", lib.find_collection_action("выключенная"), None)
    expect("картинки из своей коллекции", lib.tags_for("lib:булочка"), ["булочка"])

    expect("своя фраза коллекции", templates_for(lib.action_for("пончик")), ("{emoji} {actor} и {target}: {item}",))
    expect("стандартные фразы", templates_for(found), lib.LIBRARY_PHRASES)

    # Готовые подписи для «электрического стула»; своя фраза коллекции важнее
    lib.prime_collections([
        SimpleNamespace(tag="электрический стул", emoji="⚡", as_action=True, triggers=[], phrase=None),
        SimpleNamespace(tag="электростул", emoji="⚡", as_action=True, triggers=[], phrase="{emoji} {actor} и {target}: {item}"),
    ])
    chair = lib.SPECIAL_PHRASES[("электрическ", "электростул")]
    expect("подписи электрического стула", templates_for(lib.action_for("электрический стул")), chair)
    expect("своя фраза важнее готовых", templates_for(lib.action_for("электростул")), ("{emoji} {actor} и {target}: {item}",))
    expect("хэштег с подчёркиванием", lib.special_phrases("Электрический_стул"), chair)
    lover = lib.special_phrases("ловелас и бабник")
    expect("подписи ловеласа", lib.special_phrases("бабник"), lover)
    pool = lib.special_phrases("бильярд")
    expect("бильярд с опечаткой «бильрд»", lib.special_phrases("бильрд"), pool)
    for tag, base in (("доброеутро", "доброеутро"), ("Доброе_утро", "доброеутро"), ("обезьянка", "обезьян"),
                      ("сладких снов", "сладкихснов"), ("сднемрождения", "сднемрожд"), ("С днём рождения", "сднемрожд"), ("массаж", "массаж"), ("Массажик", "массаж")):
        found_phrases = lib.special_phrases(tag)
        expect(f"подписи для #{tag}", bool(found_phrases) and found_phrases is next(
            v for k, v in lib.SPECIAL_PHRASES.items() if base in k), True)
    # Баня — встроенное действие: картинки коллекции идут с его подписями
    from actions import phrases as builtin
    from actions.catalog import find_action as find_builtin

    banya = builtin.templates_for(find_builtin("баня"))
    expect("у бани не меньше 35 подписей без повторов", len(set(banya)) == len(banya) >= 35, True)
    for phrase in banya:
        expect(f"подпись бани проходит проверку: {phrase[:30]}", ac.validate_phrase(phrase), None)
    expect("коллекция «баня» привязана к действию бани", lib.guess_target("баня"), "banya")

    for word, minimum in (("латте", 30), ("гамбургер", 30), ("потанцевать", 20), ("смузи", 25)):
        found_templates = builtin.templates_for(find_builtin(word))
        expect(f"подписей для «{word}» не меньше {minimum}", len(set(found_templates)) == len(found_templates) >= minimum, True)
        for phrase in found_templates:
            expect(f"подпись «{word}» проходит проверку: {phrase[:30]}", ac.validate_phrase(phrase), None)

    flowers = builtin.templates_for(find_builtin("цветы"))
    expect("у цветов не меньше 40 подписей без повторов", len(set(flowers)) == len(flowers) >= 40, True)
    for phrase in flowers:
        expect(f"подпись цветов проходит проверку: {phrase[:30]}", ac.validate_phrase(phrase), None)
    expect("коллекция «цветы» привязана к действию цветов", lib.guess_target("цветы"), "flowers")

    for bases, phrases in lib.SPECIAL_PHRASES.items():
        expect(f"подписи {bases[0]} без повторов и не меньше 25", len(set(phrases)) == len(phrases) >= 25, True)
    for phrase in [p for v in lib.SPECIAL_PHRASES.values() for p in v]:
        expect(f"подпись стула проходит проверку: {phrase[:30]}", ac.validate_phrase(phrase), None)

    for phrase in lib.LIBRARY_PHRASES:
        expect(f"стандартная фраза проходит проверку: {phrase[:30]}", ac.validate_phrase(phrase), None)

    expect("пример фразы", ac.preview_phrase(lib.LIBRARY_PHRASES[0], "male", emoji="🥐", item="булочка"),
           "🥐 Стас отправил Кате: <b>булочка</b>")

    # встроенное действие важнее коллекции с тем же словом
    from settings import store

    store.prime(-500, {})
    lib.prime_collections([SimpleNamespace(tag="пиво", emoji="✨", as_action=True, triggers=[], phrase=None)])
    expect("встроенное важнее", ac.resolve(-500, "пиво").key, "beer")

    from actions.catalog import find_action

    expect("«булочка» уже есть в каталоге — привяжется к нему", (find_action("булочка") or SimpleNamespace(key=None)).key, "bun")
    expect("«булочка» → встроенное действие", lib.guess_target("булочка"), "bun")

    expect("«ватрушечка» в каталоге нет", find_action("ватрушечка"), None)
    lib.prime_collections([SimpleNamespace(tag="ватрушечка", emoji="🧁", as_action=True, triggers=[], phrase=None)])
    expect("новое слово — своё действие через общий поиск",
           (ac.resolve(-500, "ватрушечку") or SimpleNamespace(key=None)).key, "lib:ватрушечка")

    store.prime(-501, {"library": False})
    expect("группа выключила коллекцию", ac.resolve(-501, "ватрушечку"), None)

    checks += 1
    mw = (ROOT / "images_library.py").read_text(encoding="utf-8")
    if "is_owner(message.from_user.id)" not in mw[mw.index("def is_upload("):mw.index("@router.message(is_upload)")]:
        failures.append("  [права] загружать в коллекцию должен только владелец бота")

    if failures:
        print(f"❌ {len(failures)} проблем:\n")
        print("\n".join(failures))
        return 1

    print(f"✅ Все {checks} проверок коллекции прошли.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
