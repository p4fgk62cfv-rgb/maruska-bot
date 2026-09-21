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
        key="fortune",
        title="Предсказания",
        emoji="🔮",
        description="«Мара, предскажи» — одно предсказание в день на человека",
        group="Общение",
    ),
    Feature(
        key="greeting",
        title="Приветствие",
        emoji="👋",
        description="Здороваться с новыми участниками и подсказывать команды",
        group="Сообщество",
    ),
    Feature(
        key="digest",
        title="Итоги недели",
        emoji="📊",
        description="Раз в неделю подводить итоги: кто активнее, богаче, удачливее",
        group="Сообщество",
    ),
    Feature(
        key="rating",
        title="Рейтинг",
        emoji="⭐",
        description="Плюсы и минусы реплаем, /top и /profile",
        group="Сообщество",
    ),
    Feature(
        key="progress",
        title="Уровни и достижения",
        emoji="🎚",
        description="Опыт за активность, уровни и 20 достижений",
        group="Сообщество",
    ),
    Feature(
        key="economy",
        title="Алмазы",
        emoji="💎",
        description="Баланс, ежедневный бонус, награды за игры",
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


# ---------------------------------------------------------
# Настройки с выбором из списка
#
# Отличаются от переключателей тем, что хранят строку, а не
# да/нет. Добавляются так же просто: строка здесь — и вариант
# появится в панели.
# ---------------------------------------------------------

@dataclass(frozen=True)
class Choice:
    key: str
    title: str
    emoji: str
    description: str
    options: tuple[tuple[str, str, str], ...]   # (значение, подпись, эмодзи)
    default: str
    group: str = "Основное"


def _persona_options() -> tuple[tuple[str, str, str], ...]:
    from ai.personas import PERSONAS

    return tuple(
        (persona.key, persona.title, persona.emoji)
        for persona in PERSONAS
    )


CHOICES: tuple[Choice, ...] = (
    Choice(
        key="chattiness",
        title="Болтливость",
        emoji="🗣",
        description="Насколько охотно Мара вмешивается в разговор",
        options=(
            ("quiet", "Сдержанная", "🤐"),
            ("normal", "Обычная", "🙂"),
            ("active", "Болтливая", "🗯"),
        ),
        default="normal",
        group="Общение",
    ),
    Choice(
        key="persona",
        title="Характер Мары",
        emoji="🎭",
        description="Как она себя ведёт: добрая, весёлая, дерзкая, романтичная или тролль",
        options=_persona_options(),
        default="funny",
        group="Общение",
    ),
)


CHOICE_BY_KEY = {choice.key: choice for choice in CHOICES}

FEATURE_BY_KEY = {feature.key: feature for feature in FEATURES}

DEFAULTS = {feature.key: feature.default for feature in FEATURES}

DEFAULTS.update({choice.key: choice.default for choice in CHOICES})


def choices_by_group(name: str) -> list[Choice]:
    return [choice for choice in CHOICES if choice.group == name]


def option_label(key: str, value: str) -> str:
    choice = CHOICE_BY_KEY.get(key)

    if choice is None:
        return value

    for option_value, label, emoji in choice.options:
        if option_value == value:
            return f"{emoji} {label}"

    return value


def groups() -> list[str]:
    seen = []

    for item in list(FEATURES) + list(CHOICES):
        if item.group not in seen:
            seen.append(item.group)

    return seen


def by_group(name: str) -> list[Feature]:
    return [feature for feature in FEATURES if feature.group == name]
