"""
Проверка админ-панели.

Главное, что здесь проверяется: каждая функция из реестра
действительно проверяется в коде. Если добавить фичу в реестр
и забыть поставить is_enabled(), тест упадёт.

Запуск:  python test_settings.py
"""

import pathlib
import re

from settings import store
from settings.registry import DEFAULTS, FEATURE_BY_KEY, FEATURES, by_group, groups


ROOT = pathlib.Path(__file__).parent

# Где искать проверки is_enabled(...)
SOURCES = [
    ROOT / "bot.py",
    ROOT / "actions" / "handler.py",
    ROOT / "games" / "crocodile.py",
]


def collect_guarded_keys() -> set[str]:
    pattern = re.compile(r"is_enabled\([^)]*?[\"']([a-z_]+)[\"']")
    found = set()

    for path in SOURCES:
        if path.exists():
            found.update(pattern.findall(path.read_text(encoding="utf-8")))

    return found


def main() -> int:
    failures = []

    # 1. Реестр цел
    keys = [feature.key for feature in FEATURES]

    if len(keys) != len(set(keys)):
        failures.append("  [реестр] дублирующиеся ключи")

    for feature in FEATURES:
        if not feature.key.islower() or " " in feature.key:
            failures.append(f"  [реестр] плохой ключ: {feature.key!r}")
        if not feature.description:
            failures.append(f"  [реестр] нет описания: {feature.key}")

    # 2. Каждая функция реально проверяется в коде
    guarded = collect_guarded_keys()

    for feature in FEATURES:
        if feature.key not in guarded:
            failures.append(
                f"  [подключение] {feature.key!r} есть в реестре, "
                "но нигде не проверяется через is_enabled()"
            )

    for key in guarded:
        if key not in FEATURE_BY_KEY:
            failures.append(
                f"  [подключение] код проверяет {key!r}, "
                "но такой функции нет в реестре"
            )

    # 3. Кэш и значения по умолчанию
    chat = -1001

    store.forget(chat)

    for feature in FEATURES:
        if store.is_enabled(chat, feature.key) != feature.default:
            failures.append(
                f"  [умолчания] {feature.key}: без записи в базе "
                "должно браться значение по умолчанию"
            )

    store.prime(chat, {"ai": False, "неизвестный_ключ": True})

    if store.is_enabled(chat, "ai"):
        failures.append("  [кэш] выключённая функция считается включённой")

    if not store.is_enabled(chat, "actions"):
        failures.append("  [кэш] незаданная функция должна остаться по умолчанию")

    store.apply(chat, "actions", False)

    if store.is_enabled(chat, "actions"):
        failures.append("  [кэш] apply() не применился")

    # 4. В личке ограничений нет
    if not store.is_enabled(12345, "games"):
        failures.append("  [личка] в приватном чате всё должно быть доступно")

    # 5. Разбивка по разделам покрывает весь реестр
    covered = sum(len(by_group(name)) for name in groups())

    if covered != len(FEATURES):
        failures.append("  [разделы] не все функции попали в разделы")

    store.forget(chat)

    total = len(FEATURES) * 2 + 8

    if failures:
        print(f"❌ {len(failures)} проблем:\n")
        print("\n".join(failures))
        return 1

    print(
        f"✅ Все проверки прошли. Функций в реестре: {len(FEATURES)}, "
        f"разделов: {len(groups())}"
    )
    print("   включены по умолчанию: " + ", ".join(
        key for key, value in DEFAULTS.items() if value
    ))
    print("   выключены по умолчанию: " + (", ".join(
        key for key, value in DEFAULTS.items() if not value
    ) or "нет"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
