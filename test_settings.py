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
from settings.registry import (
    CHOICES,
    FEATURE_BY_KEY,
    FEATURES,
    NUMBERS,
    TEXTS,
    by_group,
    choices_by_group,
    groups,
    numbers_by_group,
    option_label,
    texts_by_group,
)


ROOT = pathlib.Path(__file__).parent

# Где искать проверки is_enabled(...)
SOURCES = [
    ROOT / "bot.py",
    ROOT / "actions" / "handler.py",
    ROOT / "games" / "crocodile.py",
    ROOT / "games" / "dice.py",
    ROOT / "economy" / "handler.py",
    ROOT / "economy" / "shop_handler.py",
    ROOT / "progress" / "handler.py",
] + sorted((ROOT / "features").glob("*.py"))


def collect_guarded_keys() -> set[str]:
    pattern = re.compile(r"is_enabled\([^)]*?[\"']([a-z_]+)[\"']")
    found = set()

    for path in SOURCES:
        if path.exists():
            found.update(pattern.findall(path.read_text(encoding="utf-8")))

    return found


def collect_text_keys() -> set[str]:
    """
    Какие текстовые настройки реально читаются кодом.
    """
    pattern = re.compile(r"get_text\([^)]*?[\"']([a-z_]+)[\"']")
    found = set()

    for path in SOURCES:
        if path.exists():
            found.update(pattern.findall(path.read_text(encoding="utf-8")))

    return found


def collect_number_keys() -> set[str]:
    """
    Какие числовые настройки реально читаются кодом.
    """
    pattern = re.compile(r"get_number\([^)]*?[\"']([a-z_]+)[\"']")
    found = set()

    extra = [
        ROOT / "economy" / "service.py",
        ROOT / "database" / "repository.py",
    ]

    for path in SOURCES + extra:
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

    # 2б. Каждая числовая настройка должна применяться в коде
    numeric = collect_number_keys()

    for number in NUMBERS:
        if number.key not in numeric:
            failures.append(
                f"  [подключение] число {number.key!r} есть в реестре, "
                "но нигде не читается через get_number()"
            )

    for key in numeric:
        if key not in {n.key for n in NUMBERS}:
            failures.append(
                f"  [подключение] код читает число {key!r}, "
                "но такой настройки нет в реестре"
            )

    # 2в. Каждый текст должен применяться в коде
    text_keys = collect_text_keys()

    for text in TEXTS:
        if text.key not in text_keys:
            failures.append(
                f"  [подключение] текст {text.key!r} есть в реестре, "
                "но нигде не читается через get_text()"
            )

    for key in text_keys:
        if key not in {t.key for t in TEXTS}:
            failures.append(
                f"  [подключение] код читает текст {key!r}, "
                "но такой настройки нет в реестре"
            )

    # Тексты осмысленны
    for text in TEXTS:
        if not text.default.strip():
            failures.append(f"  [текст] {text.key}: пустое значение по умолчанию")

        if len(text.default) > text.max_length:
            failures.append(
                f"  [текст] {text.key}: стандартный текст длиннее лимита"
            )

        # Подстановки в стандартном тексте должны быть разрешены
        import re as _re

        used = set(_re.findall(r"\{([a-z_]+)\}", text.default))

        if used - set(text.placeholders):
            failures.append(
                f"  [текст] {text.key}: в стандартном тексте есть "
                "неразрешённые подстановки"
            )

    # Границы чисел осмысленны
    for number in NUMBERS:
        if number.minimum >= number.maximum:
            failures.append(f"  [число] {number.key}: минимум не меньше максимума")

        if number.step <= 0:
            failures.append(f"  [число] {number.key}: шаг должен быть больше нуля")

        default = number.resolve_default()

        if not number.minimum <= default <= number.maximum:
            failures.append(
                f"  [число] {number.key}: значение по умолчанию "
                f"{default} вне границ"
            )

        if number.clamp(number.minimum - 1000) != number.minimum:
            failures.append(f"  [число] {number.key}: clamp не держит минимум")

        if number.clamp(number.maximum + 1000) != number.maximum:
            failures.append(f"  [число] {number.key}: clamp не держит максимум")

        if not number.label(default):
            failures.append(f"  [число] {number.key}: пустая подпись")

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
    covered = sum(
        len(by_group(name))
        + len(choices_by_group(name))
        + len(numbers_by_group(name))
        + len(texts_by_group(name))
        for name in groups()
    )

    if covered != len(FEATURES) + len(CHOICES) + len(NUMBERS) + len(TEXTS):
        failures.append("  [разделы] не все настройки попали в разделы")

    # 6. Настройки-списки: варианты корректны
    for choice in CHOICES:
        values_seen = [option[0] for option in choice.options]

        if len(values_seen) != len(set(values_seen)):
            failures.append(f"  [список] дубли вариантов в {choice.key}")

        if choice.default not in values_seen:
            failures.append(
                f"  [список] значение по умолчанию {choice.default!r} "
                f"отсутствует в вариантах {choice.key}"
            )

        for value in values_seen:
            if option_label(choice.key, value) == value:
                failures.append(
                    f"  [список] нет подписи для {choice.key}={value}"
                )

    store.forget(chat)

    total = len(FEATURES) * 2 + 8

    if failures:
        print(f"❌ {len(failures)} проблем:\n")
        print("\n".join(failures))
        return 1

    print(
        f"✅ Все проверки прошли. Параметров: {len(FEATURES)} переключателей, "
        f"{len(CHOICES)} списков, {len(NUMBERS)} чисел, "
        f"{len(TEXTS)} текстов. "
        f"Разделов: {len(groups())}"
    )
    print("   включены по умолчанию: " + ", ".join(
        f.key for f in FEATURES if f.default
    ))
    print("   выключены по умолчанию: " + (", ".join(
        f.key for f in FEATURES if not f.default
    ) or "нет"))
    for choice in CHOICES:
        print(
            f"   {choice.title}: {len(choice.options)} вариантов, "
            f"по умолчанию {option_label(choice.key, choice.default)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
