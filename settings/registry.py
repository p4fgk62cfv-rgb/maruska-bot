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

import os
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




# ---------------------------------------------------------
# Числовые настройки
#
# Третий тип: не да/нет и не выбор из списка, а величина.
# Меняется кнопками − и +, поэтому у каждой задан шаг.
#
# Значение по умолчанию берётся из переменной окружения, если она
# задана: так глобальный дефолт можно поменять для всех групп сразу,
# а конкретная группа при этом может выставить своё.
# ---------------------------------------------------------

@dataclass(frozen=True)
class Number:
    key: str
    title: str
    emoji: str
    description: str
    default: int
    minimum: int
    maximum: int
    step: int
    env: str = ""
    unit: str = ""
    group: str = "Основное"

    def resolve_default(self) -> int:
        raw = os.getenv(self.env, "").strip() if self.env else ""

        if raw.lstrip("-").isdigit():
            return self.clamp(int(raw))

        return self.default

    def clamp(self, value: int) -> int:
        return max(self.minimum, min(self.maximum, value))

    def label(self, value: int) -> str:
        if self.key == "digest_weekday":
            return WEEKDAYS[value % 7]

        if self.unit:
            return f"{value} {self.unit}"

        return str(value)


WEEKDAYS = (
    "понедельник", "вторник", "среда", "четверг",
    "пятница", "суббота", "воскресенье",
)


NUMBERS: tuple[Number, ...] = (
    # Общение
    Number(
        key="context_messages",
        title="Глубина памяти",
        emoji="🧠",
        description="Сколько последних сообщений Мара видит как контекст",
        default=8, minimum=2, maximum=30, step=2,
        env="CONTEXT_MESSAGES", unit="сообщ.",
        group="Общение",
    ),

    # Алмазы
    Number(
        key="bonus_min",
        title="Бонус: минимум",
        emoji="💎",
        description="Нижняя граница ежедневного бонуса",
        default=50, minimum=10, maximum=1000, step=10,
        env="BONUS_MIN", unit="💎",
        group="Сообщество",
    ),
    Number(
        key="bonus_max",
        title="Бонус: максимум",
        emoji="💎",
        description="Верхняя граница ежедневного бонуса",
        default=150, minimum=20, maximum=2000, step=10,
        env="BONUS_MAX", unit="💎",
        group="Сообщество",
    ),
    Number(
        key="jackpot_chance",
        title="Шанс джекпота",
        emoji="🎰",
        description="Как часто вместо бонуса выпадает крупный выигрыш",
        default=5, minimum=0, maximum=50, step=1,
        unit="%",
        group="Сообщество",
    ),

    # Прогресс
    Number(
        key="xp_message",
        title="Опыт за сообщение",
        emoji="✨",
        description="Сколько опыта даёт одно сообщение",
        default=2, minimum=0, maximum=20, step=1,
        env="XP_MESSAGE",
        group="Сообщество",
    ),
    Number(
        key="xp_daily_cap",
        title="Потолок опыта в сутки",
        emoji="🚧",
        description="Больше этого за сообщения не начислится — защита от флуда",
        default=120, minimum=20, maximum=2000, step=20,
        env="XP_DAILY_CAP",
        group="Сообщество",
    ),
    Number(
        key="rating_cooldown",
        title="Пауза рейтинга",
        emoji="⏳",
        description="Как часто можно оценивать одного и того же человека",
        default=24, minimum=1, maximum=168, step=1,
        unit="ч",
        group="Сообщество",
    ),

    # Итоги
    Number(
        key="digest_weekday",
        title="День итогов",
        emoji="📅",
        description="В какой день недели подводить итоги",
        default=6, minimum=0, maximum=6, step=1,
        env="DIGEST_WEEKDAY",
        group="Сообщество",
    ),
    Number(
        key="digest_hour",
        title="Час итогов",
        emoji="🕐",
        description="Во сколько подводить итоги, по UTC",
        default=17, minimum=0, maximum=23, step=1,
        env="DIGEST_HOUR", unit="ч UTC",
        group="Сообщество",
    ),

    # Игры
    Number(
        key="reward_game_win",
        title="Награда за победу",
        emoji="🏆",
        description="Сколько алмазов получает угадавший",
        default=25, minimum=0, maximum=500, step=5,
        env="REWARD_GAME_WIN", unit="💎",
        group="Развлечения",
    ),
    Number(
        key="reward_game_host",
        title="Награда ведущему",
        emoji="🎭",
        description="Сколько алмазов получает тот, кто рисовал",
        default=15, minimum=0, maximum=500, step=5,
        env="REWARD_GAME_HOST", unit="💎",
        group="Развлечения",
    ),
    Number(
        key="hint_cooldown",
        title="Пауза подсказки",
        emoji="💡",
        description="Через сколько можно открыть следующую букву",
        default=30, minimum=0, maximum=300, step=5,
        env="HINT_COOLDOWN", unit="сек",
        group="Развлечения",
    ),
)


NUMBER_BY_KEY = {number.key: number for number in NUMBERS}


def numbers_by_group(name: str) -> list[Number]:
    return [number for number in NUMBERS if number.group == name]




# ---------------------------------------------------------
# Текстовые настройки
#
# Четвёртый тип: свой текст вместо стандартного. Меняется
# ответом на сообщение бота — кнопками текст не наберёшь.
#
# placeholders перечисляет разрешённые подстановки. Если человек
# впишет неизвестную, настройка не сохранится: лучше отказать,
# чем потом падать при отправке.
# ---------------------------------------------------------

@dataclass(frozen=True)
class Text:
    key: str
    title: str
    emoji: str
    description: str
    default: str
    placeholders: tuple[str, ...] = ()
    max_length: int = 500
    group: str = "Основное"

    def hint(self) -> str:
        if not self.placeholders:
            return ""

        names = ", ".join(f"<code>{{{p}}}</code>" for p in self.placeholders)

        return f"Можно использовать: {names}"


DEFAULT_GREETING = "👋 <b>{name}</b>, заходи, располагайся."

DEFAULT_GREETING_HINT = (
    "Я Мара, живу в этом чате.\n\n"
    "💬 Позови по имени — поболтаем\n"
    "🎁 /bonus — забрать ежедневные алмазы\n"
    "🎲 Ответь кому-нибудь словом «пиво» или «обнять»\n"
    "❔ /help — что я ещё умею"
)


TEXTS: tuple[Text, ...] = (
    Text(
        key="greeting_text",
        title="Текст приветствия",
        emoji="👋",
        description="Первая строка, которой бот здоровается с новичком",
        default=DEFAULT_GREETING,
        placeholders=("name",),
        max_length=300,
        group="Сообщество",
    ),
    Text(
        key="greeting_hint",
        title="Подсказка новичку",
        emoji="📝",
        description="Что бот пишет новичку после приветствия",
        default=DEFAULT_GREETING_HINT,
        max_length=800,
        group="Сообщество",
    ),
)


TEXT_BY_KEY = {text.key: text for text in TEXTS}


def texts_by_group(name: str) -> list[Text]:
    return [text for text in TEXTS if text.group == name]


CHOICE_BY_KEY = {choice.key: choice for choice in CHOICES}

FEATURE_BY_KEY = {feature.key: feature for feature in FEATURES}

DEFAULTS = {feature.key: feature.default for feature in FEATURES}

DEFAULTS.update({choice.key: choice.default for choice in CHOICES})

DEFAULTS.update(
    {number.key: number.resolve_default() for number in NUMBERS}
)

DEFAULTS.update({text.key: text.default for text in TEXTS})


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

    for item in list(FEATURES) + list(CHOICES) + list(NUMBERS) + list(TEXTS):
        if item.group not in seen:
            seen.append(item.group)

    return seen


def by_group(name: str) -> list[Feature]:
    return [feature for feature in FEATURES if feature.group == name]
