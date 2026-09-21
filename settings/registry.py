"""
Реестр функций Маруськи.

ЕДИНСТВЕННОЕ место, где описываются настройки группы.
Добавляешь функцию — добавляешь сюда строку, и она сразу
появляется в /settings, получает значение по умолчанию и
может проверяться через settings.store.is_enabled().

Ничего мигрировать не нужно: значения лежат в JSON-колонке.

Поля:
    key         — ключ в базе, менять нельзя после релиза
    title       — как называется в панели
    emoji       — иконка в кнопке
    description — строка в справке панели
    default     — включено ли по умолчанию
    group       — раздел панели
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Feature:
    key: str
    title: str
    emoji: str
    description: str
    default: bool = True
    group: str = "Основное"


FEATURES: tuple[Feature, ...] = (
    Feature(
        key="ai",
        title="Ответы Мары",
        emoji="💬",
        description="Отвечает, когда зовут по имени или отвечают на её сообщение",
        group="Общение",
    ),
    Feature(
        key="actions",
        title="Действия",
        emoji="🎲",
        description="Пиво, обнять, цветы и ещё 200 действий с картинками",
        group="Общение",
    ),
    Feature(
        key="cats",
        title="Котики",
        emoji="🐱",
        description="«Покажи меня» и «мяу»",
        group="Общение",
    ),
    Feature(
        key="weather",
        title="Погода",
        emoji="🌤",
        description="«Мара, погода в Праге» и /weather",
        group="Общение",
    ),
    Feature(
        key="rating",
        title="Рейтинг",
        emoji="⭐",
        description="Плюсы и минусы реплаем, /top и /profile",
        group="Сообщество",
    ),
    Feature(
        key="games",
        title="Игры",
        emoji="🐊",
        description="Крокодил и будущие игры",
        group="Развлечения",
        default=False,
    ),
)


FEATURE_BY_KEY = {feature.key: feature for feature in FEATURES}

DEFAULTS = {feature.key: feature.default for feature in FEATURES}


def groups() -> list[str]:
    seen = []
    for feature in FEATURES:
        if feature.group not in seen:
            seen.append(feature.group)
    return seen


def by_group(name: str) -> list[Feature]:
    return [feature for feature in FEATURES if feature.group == name]
