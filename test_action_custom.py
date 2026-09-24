"""
Проверка правок действий группы: слова, фразы, задержка, картинки.
Запуск:  python test_action_custom.py
"""

import sys
import time
import pathlib
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from actions import custom as ac


def row(kind, value, key="beer", rid=1, file_id=None):
    return SimpleNamespace(id=rid, kind=kind, value=value, action_key=key, file_id=file_id)


def main() -> int:
    failures, checks = [], 0

    def expect(label, got, want):
        nonlocal checks
        checks += 1
        if got != want:
            failures.append(f"  {label}: получили {got!r}, ждали {want!r}")

    def ok(label, value):
        expect(label, bool(value), True)

    # --- слова ---
    expect("нормализация", ac.normalize_alias("  Пивка!! "), "пивка")
    expect("без @ника", ac.normalize_alias("@kate обнять"), "обнять")
    expect("ё → е", ac.normalize_alias("Ёжик"), "ежик")
    expect("хорошее слово", ac.validate_alias("пивка"), None)
    ok("короткое отклоняется", ac.validate_alias("п"))
    ok("предложение отклоняется", ac.validate_alias("дай мне пожалуйста холодного пива"))

    # --- фразы ---
    expect("хорошая фраза", ac.validate_phrase("{emoji} {actor} <угостил|угостила> {target_acc} {item_instr}"), None)
    expect("жирный можно", ac.validate_phrase("<b>{actor}</b> обнял {target_acc}"), None)
    ok("без кто-кого", ac.validate_phrase("просто текст без подстановок"))
    ok("неизвестная подстановка", ac.validate_phrase("{actor} любит {nickname}"))
    ok("сломанные скобки", ac.validate_phrase("{actor} обнял {target_acc"))
    ok("вредоносный тег", ac.validate_phrase('{actor} <img src=x onerror=alert(1)>'))
    ok("скрипт", ac.validate_phrase("{actor} <script>alert(1)</script>"))
    ok("ссылка-тег", ac.validate_phrase('{actor} <a href="x">тык</a>'))
    ok("голый амперсанд", ac.validate_phrase("{actor} & {target}"))
    ok("слишком длинная", ac.validate_phrase("{actor} " + "а" * 400))

    expect("превью мужской род",
           ac.preview_phrase("{actor} <угостил|угостила> {target_acc}", "male"),
           "Стас угостил Катю")
    expect("превью женский род",
           ac.preview_phrase("{actor} <угостил|угостила> {target_acc}", "female", actor="Лена"),
           "Лена угостила Катю")

    # --- кэш группы ---
    ac.prime(-100, [
        row("alias", "хмельнуть", rid=1),
        row("phrase", "{actor} и {target} пьют", rid=2),
        row("image", "https://x/a.jpg", rid=3),
        row("hide_image", "77", rid=4),
        row("cooldown", "30", rid=5),
        row("image_mode", "own", rid=6),
        row("alias", "ерунда", key="нет_такого", rid=7),
    ])

    custom = ac.get(-100)
    expect("своё слово", custom.aliases, {"хмельнуть": "beer"})
    expect("фразы", custom.phrases, {"beer": ["{actor} и {target} пьют"]})
    expect("картинки", [i["id"] for i in custom.images["beer"]], [3])
    expect("скрытые", custom.hidden, {77})
    expect("задержка", custom.cooldown, {"beer": 30})
    expect("неизвестное действие пропущено", "ерунда" in custom.aliases, False)

    found = ac.resolve(-100, "Хмельнуть!")
    expect("своё слово запускает действие", found.key if found else None, "beer")
    expect("в другой группе не работает", ac.resolve(-200, "хмельнуть"), None)
    expect("команда не действие", ac.resolve(-100, "/хмельнуть"), None)

    expect("скрыта", ac.is_hidden(-100, 77), True)
    expect("не скрыта", ac.is_hidden(-100, 78), False)
    expect("только свои", ac.only_own_images(-100, "beer"), True)
    expect("режим own всегда даёт свою", ac.pick_custom_image(-100, "beer")["id"], 3)

    # --- задержка ---
    expect("до первого срабатывания", ac.cooling_down(-100, "beer"), False)
    ac.mark_used(-100, "beer")
    expect("сразу после", ac.cooling_down(-100, "beer"), True)
    ac._last_used[(-100, "beer")] = time.monotonic() - 31
    expect("через 31 сек", ac.cooling_down(-100, "beer"), False)
    expect("без задержки", ac.cooling_down(-100, "wine"), False)

    if failures:
        print(f"❌ {len(failures)} проблем:\n")
        print("\n".join(failures))
        return 1

    print(f"✅ Все {checks} проверок правок действий прошли.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
