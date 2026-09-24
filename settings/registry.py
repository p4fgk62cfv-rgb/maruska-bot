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
        key="gifts",
        title="Подарки друг другу",
        emoji="🎁",
        description="/gift — подарить вещь из магазина. Работает, если включена экономика",
        group="Сообщество",
    ),
    Feature(
        key="memory",
        title="Память Мары",
        emoji="🧠",
        description="Мара помнит последние сообщения и отвечает с учётом разговора",
        group="Общение",
    ),
    Feature(
        key="autoreplies",
        title="Автоответы",
        emoji="💬",
        description="Мара отвечает на ключевые слова заготовленными фразами",
        group="Общение",
    ),
    Feature(
        key="game_crocodile",
        title="Крокодил",
        emoji="🐊",
        description="Игра «Крокодил»: /croc. Работает, если включены игры",
        group="Развлечения",
    ),
    Feature(
        key="game_dice",
        title="Кубики и рандом",
        emoji="🎲",
        description="/dice, /coin, /random, /8ball. Работает, если включены игры",
        group="Развлечения",
    ),
    Feature(
        key="automod",
        title="Автомодерация",
        emoji="🛡",
        description="Бот сам удаляет флуд, ссылки и запрещённые слова и выдаёт предупреждения",
        default=False,
        group="Модерация",
    ),
    Feature(
        key="automod_repeats",
        title="Антиповтор",
        emoji="🔁",
        description="Считать нарушением одно и то же сообщение несколько раз подряд",
        group="Модерация",
    ),
    Feature(
        key="captcha",
        title="Капча для новичков",
        emoji="🤖",
        description="Новичок жмёт «Я не бот», иначе вылетает. Нужно право ограничивать участников",
        default=False,
        group="Модерация",
    ),
    Feature(
        key="newbie_no_media",
        title="Новичкам без медиа",
        emoji="🐣",
        description="В период адаптации нельзя фото, видео, стикеры и пересланные сообщения",
        default=False,
        group="Модерация",
    ),
    Feature(
        key="automod_symbols",
        title="Антиспам символами",
        emoji="🔣",
        description="«!!!!!!!!», «аааааааа», стена из эмодзи",
        group="Модерация",
    ),
    Feature(
        key="moderation",
        title="Модерация",
        emoji="🛡",
        description="Мут, бан, выкинуть и закрыть чат — командами и из панели",
        group="Модерация",
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
        key="language",
        title="Язык Мары",
        emoji="🌍",
        description="На каком языке Мара отвечает и пишет служебные сообщения",
        options=(
            ("ru", "Русский", "🇷🇺"),
            ("en", "English", "🇬🇧"),
        ),
        default="ru",
        group="Общение",
    ),
    Choice(
        key="timezone",
        title="Часовой пояс",
        emoji="🕐",
        description="По нему считаются часы в аналитике и время итогов недели",
        options=(
            ("Europe/Prague", "Прага, Берлин, Варшава", "🇨🇿"),
            ("Europe/Kyiv", "Киев, Рига, Хельсинки", "🇺🇦"),
            ("Europe/Moscow", "Москва, Минск, Стамбул", "🇷🇺"),
            ("Asia/Almaty", "Алматы, Бишкек", "🇰🇿"),
            ("Europe/London", "Лондон, Лиссабон", "🇬🇧"),
            ("America/New_York", "Нью-Йорк", "🇺🇸"),
            ("UTC", "UTC", "🌐"),
        ),
        default="Europe/Prague",
        group="Сообщество",
    ),
    Choice(
        key="act_flood",
        title="Флуд →",
        emoji="🌊",
        description="Что делать, если: флуд",
        options=(
            ("delete", "Только удалить", "🗑"),
            ("warn", "Удалить + предупредить", "⚠️"),
            ("mute", "Удалить + мут", "🔇"),
            ("tempban", "Удалить + бан на время", "⏳"),
            ("ban", "Удалить + бан навсегда", "⛔"),
        ),
        default="warn",
        group="Модерация",
    ),
    Choice(
        key="act_repeat",
        title="Повторы →",
        emoji="🔁",
        description="Что делать, если: повторы",
        options=(
            ("delete", "Только удалить", "🗑"),
            ("warn", "Удалить + предупредить", "⚠️"),
            ("mute", "Удалить + мут", "🔇"),
            ("tempban", "Удалить + бан на время", "⏳"),
            ("ban", "Удалить + бан навсегда", "⛔"),
        ),
        default="delete",
        group="Модерация",
    ),
    Choice(
        key="act_link",
        title="Запрещённая ссылка →",
        emoji="🔗",
        description="Что делать, если: запрещённая ссылка",
        options=(
            ("delete", "Только удалить", "🗑"),
            ("warn", "Удалить + предупредить", "⚠️"),
            ("mute", "Удалить + мут", "🔇"),
            ("tempban", "Удалить + бан на время", "⏳"),
            ("ban", "Удалить + бан навсегда", "⛔"),
        ),
        default="warn",
        group="Модерация",
    ),
    Choice(
        key="act_stop_word",
        title="Стоп-слово →",
        emoji="🚫",
        description="Что делать, если: стоп-слово",
        options=(
            ("delete", "Только удалить", "🗑"),
            ("warn", "Удалить + предупредить", "⚠️"),
            ("mute", "Удалить + мут", "🔇"),
            ("tempban", "Удалить + бан на время", "⏳"),
            ("ban", "Удалить + бан навсегда", "⛔"),
        ),
        default="warn",
        group="Модерация",
    ),
    Choice(
        key="act_symbols",
        title="Спам символами →",
        emoji="🔣",
        description="Что делать, если: спам символами",
        options=(
            ("delete", "Только удалить", "🗑"),
            ("warn", "Удалить + предупредить", "⚠️"),
            ("mute", "Удалить + мут", "🔇"),
            ("tempban", "Удалить + бан на время", "⏳"),
            ("ban", "Удалить + бан навсегда", "⛔"),
        ),
        default="delete",
        group="Модерация",
    ),
    Choice(
        key="act_stickers",
        title="Много стикеров →",
        emoji="🎭",
        description="Что делать, если: много стикеров",
        options=(
            ("delete", "Только удалить", "🗑"),
            ("warn", "Удалить + предупредить", "⚠️"),
            ("mute", "Удалить + мут", "🔇"),
            ("tempban", "Удалить + бан на время", "⏳"),
            ("ban", "Удалить + бан навсегда", "⛔"),
        ),
        default="delete",
        group="Модерация",
    ),
    Choice(
        key="act_media",
        title="Много медиа →",
        emoji="🖼",
        description="Что делать, если: много медиа",
        options=(
            ("delete", "Только удалить", "🗑"),
            ("warn", "Удалить + предупредить", "⚠️"),
            ("mute", "Удалить + мут", "🔇"),
            ("tempban", "Удалить + бан на время", "⏳"),
            ("ban", "Удалить + бан навсегда", "⛔"),
        ),
        default="delete",
        group="Модерация",
    ),
    Choice(
        key="act_newbie",
        title="Нарушение новичка →",
        emoji="🐣",
        description="Что делать, если новичок нарушил свои правила: медиа, пересылка, замедление",
        options=(
            ("delete", "Только удалить", "🗑"),
            ("warn", "Удалить + предупредить", "⚠️"),
            ("mute", "Удалить + мут", "🔇"),
            ("tempban", "Удалить + бан на время", "⏳"),
            ("ban", "Удалить + бан навсегда", "⛔"),
        ),
        default="delete",
        group="Модерация",
    ),
    Choice(
        key="warn_action",
        title="Лимит предупреждений →",
        emoji="⚠️",
        description="Что происходит, когда набрано предупреждений до лимита",
        options=(
            ("mute", "Мут", "🔇"),
            ("tempban", "Бан на время", "⏳"),
            ("ban", "Бан навсегда", "⛔"),
        ),
        default="mute",
        group="Модерация",
    ),
    Choice(
        key="link_policy",
        title="Ссылки",
        emoji="🔗",
        description="Кому нельзя присылать ссылки",
        options=(
            ("allow", "Можно всем", "✅"),
            ("newbies", "Нельзя новичкам", "🐣"),
            ("everyone", "Нельзя никому", "⛔"),
        ),
        default="allow",
        group="Модерация",
    ),
    Choice(
        key="chattiness",
        title="Болтливость",
        emoji="🗣",
        description="Насколько охотно Мара вмешивается в разговор",
        options=(
            ("quiet", "Сдержанная", "🤐"),
            ("normal", "Обычная", "🙂"),
            ("active", "Болтливая", "🗯"),
            ("fun", "Развлекательная", "🎉"),
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
        key="memory_days",
        title="Память: срок хранения",
        emoji="🗓",
        description="Сколько дней хранить сообщения группы в базе",
        default=30, minimum=1, maximum=365, step=1,
        unit="дн",
        group="Общение",
    ),
    Number(
        key="ai_daily_limit",
        title="AI: ответов в сутки",
        emoji="🤖",
        description="Сколько раз в сутки Мара отвечает в группе. 0 — без ограничений",
        default=0, minimum=0, maximum=5000, step=50,
        group="Общение",
    ),
    Number(
        key="ai_cooldown",
        title="AI: пауза для одного человека",
        emoji="⏱",
        description="Не чаще, чем раз в N секунд одному и тому же человеку. 0 — без паузы",
        default=0, minimum=0, maximum=600, step=5,
        unit="сек",
        group="Общение",
    ),
    Number(
        key="image_limit_hour",
        title="Картинок в час",
        emoji="🖼",
        description="Сколько картинок действий в час. Сверх лимита — действие без картинки. 0 — без ограничений",
        default=0, minimum=0, maximum=500, step=5,
        group="Общение",
    ),
    Number(
        key="dice_cooldown",
        title="Кубики: пауза",
        emoji="🎲",
        description="Не чаще, чем раз в N секунд одному человеку",
        default=0, minimum=0, maximum=300, step=5,
        unit="сек",
        group="Развлечения",
    ),
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
        key="xp_action",
        title="Опыт за Action",
        emoji="⚡",
        description="Сколько опыта получает тот, кто сделал действие: угостил, обнял…",
        default=3, minimum=0, maximum=50, step=1,
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

    # Модерация
    Number(
        key="flood_messages",
        title="Антифлуд: сообщений",
        emoji="🌊",
        description="Сколько сообщений подряд можно, прежде чем это флуд",
        default=6, minimum=3, maximum=30, step=1,
        group="Модерация",
    ),
    Number(
        key="flood_seconds",
        title="Антифлуд: за секунд",
        emoji="⏱",
        description="За какое время считаются сообщения",
        default=10, minimum=3, maximum=120, step=1,
        unit="сек",
        group="Модерация",
    ),
    Number(
        key="warn_limit",
        title="Предупреждений до мута",
        emoji="⚠️",
        description="После скольких предупреждений автоматический мут",
        default=3, minimum=1, maximum=10, step=1,
        group="Модерация",
    ),
    Number(
        key="punish_minutes",
        title="Срок наказания",
        emoji="⏱",
        description="На сколько минут мут или временный бан от автомодерации",
        default=60, minimum=5, maximum=43200, step=5,
        unit="мин",
        group="Модерация",
    ),
    Number(
        key="sticker_limit",
        title="Стикеров в минуту",
        emoji="🎭",
        description="Больше — нарушение. 0 — без ограничений",
        default=0, minimum=0, maximum=30, step=1,
        group="Модерация",
    ),
    Number(
        key="media_limit",
        title="Медиа в минуту",
        emoji="🖼",
        description="Фото, видео, гифки. Больше — нарушение. 0 — без ограничений",
        default=0, minimum=0, maximum=30, step=1,
        group="Модерация",
    ),
    Number(
        key="captcha_minutes",
        title="Капча: время на ответ",
        emoji="⏳",
        description="Сколько минут у новичка, чтобы нажать «Я не бот»",
        default=3, minimum=1, maximum=30, step=1,
        unit="мин",
        group="Модерация",
    ),
    Number(
        key="newbie_slowmode",
        title="Новичкам: замедление",
        emoji="🐢",
        description="Не чаще одного сообщения в N секунд в период адаптации. 0 — без замедления",
        default=0, minimum=0, maximum=600, step=5,
        unit="сек",
        group="Модерация",
    ),
    Number(
        key="newbie_hours",
        title="Новичок первые",
        emoji="🐣",
        description="Сколько часов после входа человек считается новичком",
        default=24, minimum=1, maximum=168, step=1,
        unit="ч",
        group="Модерация",
    ),
    Number(
        key="mute_minutes",
        title="Мут по умолчанию",
        emoji="🔇",
        description="На сколько минут /mute, если время не указано",
        default=60, minimum=1, maximum=10080, step=10,
        unit="мин",
        group="Модерация",
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
        key="karma_game_win",
        title="Рейтинг за игру",
        emoji="⭐",
        description="Сколько рейтинга получают угадавший и ведущий",
        default=1, minimum=0, maximum=10, step=1,
        group="Развлечения",
    ),
    Number(
        key="xp_game_win",
        title="Опыт за победу",
        emoji="✨",
        description="Сколько опыта получает угадавший",
        default=60, minimum=0, maximum=500, step=10,
        env="XP_GAME_WIN",
        group="Развлечения",
    ),
    Number(
        key="xp_game_host",
        title="Опыт ведущему",
        emoji="✨",
        description="Сколько опыта получает тот, кто рисовал",
        default=40, minimum=0, maximum=500, step=10,
        env="XP_GAME_HOST",
        group="Развлечения",
    ),
    Number(
        key="hint_max_percent",
        title="Подсказки: максимум букв",
        emoji="🔤",
        description="Какую часть слова можно открыть подсказками",
        default=50, minimum=10, maximum=90, step=10,
        unit="%",
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
    # Списки (исключения и т. п.) законно бывают пустыми
    allow_empty: bool = False

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
        key="disabled_commands",
        title="Отключённые команды",
        emoji="⛔",
        description="Команды, которые в группе работают только у админов. Через запятую: /dice, /coin",
        default="",
        max_length=500,
        group="Сообщество",
        allow_empty=True,
    ),
    Text(
        key="memory_except",
        title="Память: исключения",
        emoji="🙈",
        description="Чьи сообщения Мара не запоминает: @username или ID через запятую",
        default="",
        max_length=1000,
        group="Общение",
        allow_empty=True,
    ),
    Text(
        key="link_whitelist",
        title="Разрешённые домены",
        emoji="✅",
        description="Ссылки на эти сайты можно всегда. Через запятую",
        default="youtube.com, youtu.be, instagram.com, t.me",
        max_length=1000,
        group="Модерация",
    ),
    Text(
        key="link_blacklist",
        title="Запрещённые домены",
        emoji="⛔",
        description="Ссылки на эти сайты — нарушение всегда, даже если ссылки разрешены",
        default="bit.ly, tinyurl.com",
        max_length=1000,
        group="Модерация",
    ),
    Text(
        key="stop_words_except",
        title="Исключения из стоп-слов",
        emoji="🟢",
        description="Фразы, которые можно, даже если внутри стоп-слово",
        default="казино рояль",
        max_length=1000,
        group="Модерация",
    ),
    Text(
        key="stop_words",
        title="Стоп-слова",
        emoji="🚫",
        description="Слова через запятую — сообщения с ними автомодерация удаляет",
        default="казино, ставки на спорт, заработок в интернете",
        max_length=1500,
        group="Модерация",
    ),
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
