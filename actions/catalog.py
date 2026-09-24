"""
Каталог действий.

Главное отличие от старой версии:
действие распознаётся ТОЛЬКО как короткая самостоятельная фраза,
а не как случайная подстрока внутри обычного сообщения.

Правила распознавания:

1. Сообщение разбивается на слова (буквы, без пунктуации).
2. Служебные слова ("а", "ну", "маруська", "плиз"...) отбрасываются.
3. Если значимых слов больше MAX_ACTION_WORDS — это не действие.
4. Алиас сравнивается с НАЧАЛОМ слова, хвост не длиннее ALIAS_TAIL.
5. Алиас с префиксом "=" требует точного совпадения слова целиком
   (для коротких и двусмысленных: "тако", "вода", "суп", "пять"...).
6. Стоп-лист BLACKLIST гасит заведомые ложные срабатывания.
"""


import re

from actions.catalog_data import (  # noqa: F401
    ACTIONS,
    ACTION_BY_KEY,
    Action,
    excluded_tags,
    required_tags,
)



# ---------------------------------------------------------
# Параметры распознавания
# ---------------------------------------------------------

MAX_ACTION_WORDS = 3   # действие — короткая фраза, не предложение

# Сколько букв можно "дописать" после алиаса.
# У длинных основ хвост больше: "поцелу" -> "поцеловать".
ALIAS_TAIL_SHORT = 3
ALIAS_TAIL_LONG = 5
LONG_ALIAS_FROM = 6


def _allowed_tail(needle: str) -> int:
    return (
        ALIAS_TAIL_LONG
        if len(needle) >= LONG_ALIAS_FROM
        else ALIAS_TAIL_SHORT
    )

_WORD_RE = re.compile(r"[А-Яа-яЁёA-Za-z]+(?:-[А-Яа-яЁёA-Za-z]+)?")

# Слова, которые не мешают распознать действие.
STOP_WORDS = {
    "маруська", "маруся", "маруськa", "бот",
    "я", "ты", "он", "она", "мы", "вы", "они",
    "мне", "тебе", "ему", "ей", "нам", "вам", "им",
    "меня", "тебя", "его", "ее", "её", "их", "нас", "вас",
    "а", "и", "но", "да", "ну", "же", "бы", "ли", "вот", "тут", "там",
    "это", "эт", "так",
    "давай", "дай", "держи", "лови",
    "плиз", "пожалуйста", "спасибо", "пж",
    "на", "с", "со", "за", "по", "в", "во", "к", "ко", "у", "от", "для",
}

# Явные ложные срабатывания.
BLACKLIST = {
    "супер", "суперски", "суперский", "супруг", "супруга", "супругой",
    "сокол", "соколов", "чайник", "чайники",
    "винил", "винить", "виноват", "виновата", "виновен",
    "джинсы", "джинса", "джинсов",
    "мясник", "мясная", "рыбак",
    "пастух", "пастор", "паства",
    "розетка", "розыгрыш", "розовый", "розовая",
    "цветной", "цветная", "цветение",
    "пятница", "пятницу", "пятницы", "пятьсот", "пятый", "пятая", "пятно",
    "опять", "повод", "поводу", "завод", "провод", "проводи",
    "высокий", "высоко", "громко", "ромашка", "мороз",
    "около", "калории",
    "жмёт", "жмет", "жмут",
    "блин",  # чаще междометие, чем еда
}


# Глаголы намерения. Их наличие рядом с предметом не мешает
# распознать действие: "угости пивом", "вызвал дурку".
ACTION_VERBS = {
    "угости", "угостить", "угощаю", "угощу", "угостил", "угостила",
    "налей", "наливай", "налил", "налила", "разлей", "разлил", "разлила",
    "напои", "напоил", "напоила", "накорми", "покорми", "накормил",
    "накормила", "подари", "дарю", "подарил", "подарила", "вручи",
    "вручил", "вручила", "принеси", "неси", "принёс", "принес",
    "принесла", "закажи", "заказал", "заказала", "купи", "купил",
    "купила", "отдай", "отдам", "отдал", "отдала", "поставь",
    "поставил", "поставила", "передай", "передал", "передала",
    "скинь", "скинул", "скинула", "кидаю", "отправь", "отправил",
    "отправила", "вызови", "вызывай", "вызвал", "вызвала", "зови",
    "позови", "позвал", "позвала",
}


def _normalize(word: str) -> str:
    return word.lower().replace("ё", "е")


def find_action(text: str | None, hidden: dict | None = None) -> Action | None:
    """
    Возвращает Action, если сообщение является коротким действием.
    Во всех остальных случаях — None (и тогда сообщение уходит в AI).
    """
    if not text:
        return None

    stripped = text.strip()

    # Команды и длинные простыни — точно не действия.
    if stripped.startswith("/"):
        return None

    raw_words = [_normalize(w) for w in _WORD_RE.findall(stripped)]
    if not raw_words:
        return None

    if any(word in BLACKLIST for word in raw_words):
        return None

    words = [w for w in raw_words if w not in STOP_WORDS]
    if not words:
        return None

    if len(words) > MAX_ACTION_WORDS:
        return None

    phrase = " ".join(words)

    best: Action | None = None
    best_score = 0
    best_alias = ""

    for action in ACTIONS:
        skip = hidden.get(action.key, ()) if hidden else ()

        for alias in action.aliases:
            # Слово, скрытое в этой группе, действие не запускает
            if alias in skip:
                continue

            exact = alias.startswith("=")
            needle = _normalize(alias[1:] if exact else alias)

            score = len(needle)
            if score <= best_score:
                continue

            if " " in needle:
                matched = needle in phrase
            elif exact:
                matched = any(word == needle for word in words)
            else:
                tail = _allowed_tail(needle)
                matched = any(
                    word.startswith(needle)
                    and len(word) - len(needle) <= tail
                    for word in words
                )

            if matched:
                best = action
                best_score = score
                best_alias = needle

    if best is None:
        return None

    # Главная защита от флуда: в сообщении не должно быть ничего,
    # кроме самого действия. "Пиво" — команда, "тоже кошку" — реплика
    # в разговоре, и лезть туда с картинкой бот не должен.
    if _has_extra_words(words, best, best_alias):
        return None

    return best


def _word_belongs(word: str, action: Action, best_alias: str) -> bool:
    if word in best_alias.split():
        return True

    for alias in action.aliases:
        needle = _normalize(alias.lstrip("="))

        if " " in needle:
            if word in needle.split():
                return True
            continue

        if alias.startswith("="):
            if word == needle:
                return True
            continue

        if (
            word.startswith(needle)
            and len(word) - len(needle) <= _allowed_tail(needle)
        ):
            return True

    return False


def _has_extra_words(
    words: list[str],
    action: Action,
    best_alias: str,
) -> bool:
    for word in words:
        if word in ACTION_VERBS:
            continue

        if _word_belongs(word, action, best_alias):
            continue

        return True

    return False
