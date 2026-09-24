"""
Язык служебных сообщений Мары.

Переведено то, что бот говорит сам: ответы AI (через инструкцию
модели), капча, автомодерация, команды модерации, приветствие.

НЕ переведено и остаётся на русском: фразы 205 действий,
предсказания, слова крокодила, магазин, достижения. Это сотни
авторских текстов — их нужно переводить с носителем языка, а не
машинально.

t(chat_id, "ключ", name="Стас") → строка на языке группы.
Нет перевода — берётся русский вариант, чтобы бот не замолчал.
"""

LANGUAGES = ("ru", "en")

AI_INSTRUCTION = {
    "ru": "",
    "en": "Always reply in English, even if the user writes in another language.\n\n",
}

TEXTS = {
    # --- автомодерация ---
    "reason.flood": {"ru": "флуд", "en": "flooding"},
    "reason.repeat": {"ru": "повтор одного и того же", "en": "repeating the same message"},
    "reason.link": {"ru": "запрещённая ссылка", "en": "forbidden link"},
    "reason.stop_word": {"ru": "запрещённое слово", "en": "forbidden word"},
    "reason.symbols": {"ru": "спам символами", "en": "symbol spam"},
    "reason.stickers": {"ru": "слишком много стикеров", "en": "too many stickers"},
    "reason.media": {"ru": "слишком много медиа", "en": "too much media"},
    "reason.newbie": {"ru": "ограничение для новичков", "en": "newcomer restriction"},
    "reason.warn_limit": {"ru": "{limit} предупреждений", "en": "{limit} warnings"},

    "mod.muted": {"ru": "🔇 <b>{name}</b> помолчит {minutes} мин — {reason}.",
                  "en": "🔇 <b>{name}</b> is muted for {minutes} min — {reason}."},
    "mod.tempbanned": {"ru": "⏳ <b>{name}</b> забанен на {minutes} мин — {reason}.",
                       "en": "⏳ <b>{name}</b> is banned for {minutes} min — {reason}."},
    "mod.banned": {"ru": "⛔ <b>{name}</b> забанен — {reason}.",
                   "en": "⛔ <b>{name}</b> is banned — {reason}."},
    "mod.warned": {"ru": "⚠️ <b>{name}</b>, {reason}. Предупреждение {total} из {limit}.",
                   "en": "⚠️ <b>{name}</b>, {reason}. Warning {total} of {limit}."},

    # --- команды модерации ---
    "cmd.mute": {"ru": "🔇 <b>{name}</b> помолчит {span}.", "en": "🔇 <b>{name}</b> is muted for {span}."},
    "cmd.unmute": {"ru": "🔊 <b>{name}</b> снова может писать.", "en": "🔊 <b>{name}</b> can write again."},
    "cmd.ban": {"ru": "⛔ <b>{name}</b> забанен.", "en": "⛔ <b>{name}</b> is banned."},
    "cmd.tempban": {"ru": "⏳ <b>{name}</b> забанен на {span}.", "en": "⏳ <b>{name}</b> is banned for {span}."},
    "cmd.unban": {"ru": "✅ <b>{name}</b> разбанен.", "en": "✅ <b>{name}</b> is unbanned."},
    "cmd.kick": {"ru": "👢 <b>{name}</b> выставлен за дверь. Вернуться может по ссылке.",
                 "en": "👢 <b>{name}</b> was removed. They can rejoin via the invite link."},
    "cmd.lock": {"ru": "🔒 Чат закрыт. Писать могут только администраторы.\n/unlock — открыть.",
                 "en": "🔒 Chat is closed. Only admins can write.\n/unlock — open it."},
    "cmd.unlock": {"ru": "🔓 Чат открыт, пишите.", "en": "🔓 Chat is open, go ahead."},

    # --- капча ---
    "captcha.ask": {
        "ru": "👋 <b>{name}</b>, добро пожаловать! Нажми кнопку ниже в течение {minutes} мин — "
              "так я пойму, что ты не бот. Пока не нажмёшь, писать нельзя.",
        "en": "👋 <b>{name}</b>, welcome! Press the button below within {minutes} min "
              "so I know you are not a bot. You can't write until you do.",
    },
    "captcha.button": {"ru": "✅ Я не бот", "en": "✅ I'm not a bot"},
    "captcha.passed": {"ru": "✅ <b>{name}</b>, спасибо! Теперь можно писать.",
                       "en": "✅ <b>{name}</b>, thanks! You can write now."},
    "captcha.not_you": {"ru": "Эта кнопка не для тебя 🙂", "en": "This button is not for you 🙂"},
    "captcha.failed": {"ru": "🚪 <b>{name}</b> не прошёл проверку и удалён из группы.",
                       "en": "🚪 <b>{name}</b> didn't pass the check and was removed."},

    # --- приветствие по умолчанию ---
    "greet.default": {"ru": "👋 <b>{name}</b>, заходи, располагайся.",
                      "en": "👋 <b>{name}</b>, come in and make yourself at home."},
    "greet.hint": {
        "ru": "Я Мара, живу в этом чате.\n\n💬 Позови по имени — поболтаем\n"
              "🎁 /bonus — забрать ежедневные алмазы\n❔ /help — что я ещё умею",
        "en": "I'm Mara, I live in this chat.\n\n💬 Call me by name to chat\n"
              "🎁 /bonus — claim your daily diamonds\n❔ /help — what else I can do",
    },
}


def language(chat_id: int | None) -> str:
    if chat_id is None or chat_id >= 0:
        return "ru"

    try:
        from settings.store import get_value

        value = get_value(chat_id, "language")
    except Exception:
        value = None

    return value if value in LANGUAGES else "ru"


def t(chat_id: int | None, key: str, **values) -> str:
    variants = TEXTS.get(key, {})
    template = variants.get(language(chat_id)) or variants.get("ru") or key

    try:
        return template.format(**values)
    except (KeyError, IndexError, ValueError):
        return template


def ai_instruction(chat_id: int | None) -> str:
    return AI_INSTRUCTION.get(language(chat_id), "")
