"""
Автомодерация.

Нарушения:
    flood      — слишком много сообщений за короткое время
    repeat     — одно и то же сообщение несколько раз
    link       — ссылка (по правилам группы, с белым и чёрным списком доменов)
    stop_word  — запрещённое слово (с вариантами написания и исключениями)
    symbols    — спам символами: «!!!!!!!!», «аааааааа», стена эмодзи
    stickers   — слишком много стикеров подряд
    media      — слишком много фото/видео/гифок подряд

Конструктор наказаний «условие → действие»:
    у каждого нарушения своё действие в настройках (act_<нарушение>):
        delete / warn / mute / tempban / ban
    плюс эскалация: набрал N предупреждений → warn_action на punish_minutes

Проверка идёт в памяти, без базы. Администраторов не трогает.
"""

import logging
import re
import time
from collections import defaultdict, deque
from html import escape
from urllib.parse import urlparse

from aiogram import Router
from aiogram.types import Message

import audit

from botcontext import display_name_of

from settings.store import get_number, get_text, get_value, is_enabled

from i18n import t as _t


logger = logging.getLogger("maruska.automod")

router = Router(name="automod")


VIOLATIONS = ("flood", "repeat", "link", "stop_word", "symbols", "stickers", "media", "newbie")

REASONS = {
    "flood": "флуд",
    "repeat": "повтор одного и того же",
    "link": "запрещённая ссылка",
    "stop_word": "запрещённое слово",
    "symbols": "спам символами",
    "stickers": "слишком много стикеров",
    "media": "слишком много медиа",
    "newbie": "ограничение для новичков",
}


def reason_text(chat_id: int, violation: str) -> str:
    from i18n import t

    return t(chat_id, f"reason.{violation}")

# Какая настройка задаёт действие для каждого нарушения.
# Явный список, а не f"act_{...}": так тест видит, что каждое
# правило из панели реально читается кодом.
ACTION_SETTINGS = {
    "flood": "act_flood",
    "repeat": "act_repeat",
    "link": "act_link",
    "stop_word": "act_stop_word",
    "symbols": "act_symbols",
    "stickers": "act_stickers",
    "media": "act_media",
    "newbie": "act_newbie",
}

MEDIA_WINDOW = 60  # секунд — окно для стикеров и медиа


# =========================================================
# Чистые проверки — их покрывают тесты
# =========================================================

LINK_RE = re.compile(
    r"(https?://\S+|www\.\S+|t\.me/\S+|telegram\.me/\S+|@\w{5,}bot\b|"
    r"\b[\w-]+(?:\.[\w-]+)*\.(?:com|ru|net|org|io|me|xyz|top|site|online|shop|info|biz|club|pro|su|ua|by|kz|cz|de)\b\S*)",
    re.IGNORECASE,
)


def has_link(text: str) -> bool:
    return bool(LINK_RE.search(text or ""))


def extract_domains(text: str) -> list[str]:
    """
    Домены из всех ссылок в тексте: «https://www.Spam.ru/x» → «spam.ru».
    t.me и @бот считаются доменом «t.me».
    """
    domains = []

    for match in LINK_RE.finditer(text or ""):
        raw = match.group(0)

        if raw.startswith("@"):
            domains.append("t.me")
            continue

        if not re.match(r"https?://", raw, re.IGNORECASE):
            raw = "http://" + raw

        try:
            host = (urlparse(raw).hostname or "").lower()
        except ValueError:
            continue

        if host.startswith("www."):
            host = host[4:]

        if host == "telegram.me":
            host = "t.me"

        if host:
            domains.append(host)

    return domains


def parse_list(raw: str) -> list[str]:
    return [
        item.strip().lower()
        for item in re.split(r"[,\n;]", raw or "")
        if len(item.strip()) >= 2
    ]


def domain_matches(domain: str, patterns: list[str]) -> bool:
    """spam.ru совпадает с «spam.ru» и с поддоменами: a.spam.ru."""
    for pattern in patterns:
        pattern = pattern.lstrip("*.")

        if pattern.startswith("www."):
            pattern = pattern[4:]

        if domain == pattern or domain.endswith("." + pattern):
            return True

    return False


def link_verdict(text: str, policy: str, newbie: bool,
                 whitelist: list[str], blacklist: list[str]) -> bool:
    """
    Нарушение ли ссылка:
      - домен из чёрного списка — всегда нарушение;
      - только домены из белого списка — всегда можно;
      - остальное — по правилу группы: allow / newbies / everyone.
    """
    domains = extract_domains(text)

    if not domains:
        return False

    if any(domain_matches(d, blacklist) for d in domains):
        return True

    if all(domain_matches(d, whitelist) for d in domains):
        return False

    if policy == "everyone":
        return True

    if policy == "newbies":
        return newbie

    return False


# Латиница и цифры, похожие на кириллицу: «kaзинo», «к@зин0»
LOOKALIKES = str.maketrans({
    "a": "а", "e": "е", "o": "о", "p": "р", "c": "с", "x": "х", "y": "у",
    "k": "к", "m": "м", "t": "т", "b": "в", "h": "н", "u": "и", "n": "п",
    "0": "о", "3": "з", "4": "ч", "6": "б", "@": "а", "$": "с", "ё": "е",
})


def normalize(text: str) -> str:
    """
    Приводит текст к виду, в котором не спрятать слово:
      - похожие латинские буквы и цифры → кириллица;
      - «к.а.з.и.н.о» и «к а з и н о» → «казино»;
      - повторы букв схлопываются: «казииино» → «казино».
    """
    lowered = (text or "").lower().translate(LOOKALIKES)

    # Цепочки одиночных букв через разделители склеиваем целиком
    lowered = re.sub(
        r"\b(?:[а-я][\s.\-_*]+){2,}[а-я]\b",
        lambda m: re.sub(r"[\s.\-_*]+", "", m.group(0)),
        lowered,
    )

    # Повторы одной буквы
    lowered = re.sub(r"([а-я])\1{2,}", r"\1", lowered)

    return lowered


def find_stop_word(text: str, words: list[str], exceptions: list[str] | None = None) -> str | None:
    """
    Ищет запрещённое слово с начала слова — «казино» ловит и
    «казиношка». Исключения — фразы, которые можно, даже если
    внутри есть стоп-слово.
    """
    plain = normalize(text)

    for phrase in exceptions or []:
        plain = plain.replace(normalize(phrase), " ")

    for word in words:
        needle = normalize(word)

        if needle and re.search(rf"(?<![а-яa-z]){re.escape(needle)}", plain):
            return word

    return None


EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF]")


def is_symbol_spam(text: str) -> bool:
    """«!!!!!!!!!!!!!!!», «ааааааааааааааа», стена из 20+ эмодзи."""
    if not text:
        return False

    if re.search(r"(.)\1{14,}", text):
        return True

    if len(EMOJI_RE.findall(text)) >= 20:
        return True

    letters = sum(ch.isalpha() for ch in text)

    return len(text) >= 30 and letters / len(text) < 0.15


def is_flood(times: deque, now: float, limit: int, window: int) -> bool:
    return sum(1 for t in times if now - t <= window) > limit


def is_repeat(texts: deque, text: str, limit: int = 3) -> bool:
    normalized = " ".join((text or "").lower().split())

    if len(normalized) < 3:
        return False

    return sum(1 for t in texts if t == normalized) >= limit


def newbie_verdict(has_media: bool, forwarded: bool, no_media: bool,
                   slowmode: int, times: deque, now: float) -> str | None:
    """
    Правила периода адаптации. times уже содержит текущее сообщение,
    поэтому для замедления смотрим на предыдущее.
    """
    if no_media and (has_media or forwarded):
        return "newbie"

    if slowmode and len(times) >= 2 and now - times[-2] < slowmode:
        return "newbie"

    return None


def count_recent(times: deque, now: float, window: int) -> int:
    return sum(1 for t in times if now - t <= window)


# =========================================================
# Состояние в памяти
# =========================================================

def _ring(size):
    return defaultdict(lambda: defaultdict(lambda: deque(maxlen=size)))


_timeline = _ring(40)
_texts = _ring(6)
_stickers = _ring(30)
_media = _ring(30)

_joined: dict[tuple[int, int], float] = {}
_admin_cache: dict[tuple[int, int], tuple[float, bool]] = {}
_verdicts: dict[tuple[int, int], str] = {}

# История нарушений: (чат, человек) -> [(время, нарушение)]
_history: dict[tuple[int, int], deque] = defaultdict(lambda: deque(maxlen=100))

# Свои правила группы, по порядку
_rules: dict[int, list] = {}


def prime_rules(chat_id: int, rows) -> None:
    _rules[chat_id] = [
        {"violation": r.violation, "count": r.count, "window": r.window_minutes,
         "action": r.action, "duration": r.duration_minutes}
        for r in sorted(rows, key=lambda r: (r.position, r.id))
        if r.enabled
    ]


async def reload_rules(chat_id: int) -> None:
    from database.repository import list_punish_rules

    prime_rules(chat_id, await list_punish_rules(chat_id))


def match_rule(rules: list, history, violation: str, now: float) -> dict | None:
    """
    Первое правило, условие которого выполнено: нарушений нужного
    вида (или любых) за окно — не меньше заданного числа.
    Чистая функция — её проверяют тесты.
    """
    for rule in rules:
        if rule["violation"] not in ("any", violation):
            continue

        window = rule["window"] * 60
        hits = sum(
            1 for at, kind in history
            if now - at <= window and (rule["violation"] == "any" or kind == rule["violation"])
        )

        if hits >= rule["count"]:
            return rule

    return None


RULE_ACTIONS = {"delete": "удалить", "warn": "предупредить", "mute": "мут",
                "tempban": "бан", "ban": "бан навсегда"}


def describe_rule(rule: dict) -> str:
    """Правило человеческими словами — для панели и журнала."""
    what = "любое нарушение" if rule["violation"] == "any" else REASONS.get(rule["violation"], rule["violation"])
    times = f"{rule['count']} раз" if rule["count"] > 1 else "1 раз"
    act = rule["action"]

    if act in ("mute", "tempban"):
        hours = rule["duration"] / 60
        span = f"{rule['duration']} мин" if rule["duration"] < 60 else (
            f"{hours:g} ч" if hours < 24 else f"{hours / 24:g} дн")
        tail = ("мут на " if act == "mute" else "бан на ") + span
    else:
        tail = RULE_ACTIONS.get(act, act)

    return f"Если {what} — {times} за {rule['window']} мин → {tail}"


def remember_join(chat_id: int, user_id: int) -> None:
    _joined[(chat_id, user_id)] = time.monotonic()


def is_newbie(chat_id: int, user_id: int) -> bool:
    joined = _joined.get((chat_id, user_id))
    hours = get_number(chat_id, "newbie_hours") or 24
    return joined is not None and time.monotonic() - joined < hours * 3600


def detect(message: Message) -> str | None:
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text or message.caption or ""
    now = time.monotonic()

    _timeline[chat_id][user_id].append(now)

    texts = _texts[chat_id][user_id]
    repeated = bool(text) and is_repeat(texts, text)

    if text:
        texts.append(" ".join(text.lower().split()))

    if message.sticker:
        _stickers[chat_id][user_id].append(now)

    if message.photo or message.video or message.animation or message.document or message.video_note:
        _media[chat_id][user_id].append(now)

    if is_newbie(chat_id, user_id):
        verdict = newbie_verdict(
            has_media=bool(message.photo or message.video or message.animation or message.document
                           or message.video_note or message.sticker or message.voice),
            forwarded=bool(getattr(message, "forward_origin", None) or getattr(message, "forward_date", None)),
            no_media=is_enabled(chat_id, "newbie_no_media"),
            slowmode=get_number(chat_id, "newbie_slowmode") or 0,
            times=_timeline[chat_id][user_id],
            now=now,
        )

        if verdict:
            return verdict

    if is_flood(
        _timeline[chat_id][user_id], now,
        get_number(chat_id, "flood_messages") or 6,
        get_number(chat_id, "flood_seconds") or 10,
    ):
        return "flood"

    if repeated and is_enabled(chat_id, "automod_repeats"):
        return "repeat"

    sticker_limit = get_number(chat_id, "sticker_limit") or 0

    if message.sticker and sticker_limit and count_recent(_stickers[chat_id][user_id], now, MEDIA_WINDOW) > sticker_limit:
        return "stickers"

    media_limit = get_number(chat_id, "media_limit") or 0

    if not message.sticker and media_limit and count_recent(_media[chat_id][user_id], now, MEDIA_WINDOW) > media_limit:
        return "media"

    if text and link_verdict(
        text,
        get_value(chat_id, "link_policy") or "allow",
        is_newbie(chat_id, user_id),
        parse_list(get_text(chat_id, "link_whitelist")),
        parse_list(get_text(chat_id, "link_blacklist")),
    ):
        return "link"

    if text and is_enabled(chat_id, "automod_symbols") and is_symbol_spam(text):
        return "symbols"

    words = parse_list(get_text(chat_id, "stop_words"))

    if text and words and find_stop_word(text, words, parse_list(get_text(chat_id, "stop_words_except"))):
        return "stop_word"

    return None


def is_candidate(message: Message) -> bool:
    if message.chat.type not in ("group", "supergroup"):
        return False

    if message.from_user is None or message.from_user.is_bot:
        return False

    if not is_enabled(message.chat.id, "automod"):
        return False

    verdict = detect(message)

    if verdict is None:
        return False

    if len(_verdicts) > 500:
        _verdicts.clear()

    _verdicts[(message.chat.id, message.message_id)] = verdict

    return True


async def _is_admin(bot, chat_id: int, user_id: int) -> bool:
    key = (chat_id, user_id)
    cached = _admin_cache.get(key)

    if cached and time.monotonic() - cached[0] < 300:
        return cached[1]

    try:
        member = await bot.get_chat_member(chat_id, user_id)
        admin = member.status in ("creator", "administrator")
    except Exception:
        admin = False

    _admin_cache[key] = (time.monotonic(), admin)
    return admin


# =========================================================
# Наказания — общие для автомодерации, ручных предупреждений
# и панели
# =========================================================

async def apply_punishment(bot, chat_id: int, user_id: int, user_name: str,
                           action: str, minutes: int, reason: str,
                           actor_kind: str = "bot", actor_id: int | None = None,
                           actor_name: str | None = None, notify=None) -> str:
    """
    Применяет действие и возвращает, что реально сделано:
    warn / mute / tempban / ban / failed / none.
    """
    from features.moderation import ModerationError, ban, mute, tempban

    if action == "warn":
        return await warn(bot, chat_id, user_id, user_name, reason,
                          actor_kind=actor_kind, actor_id=actor_id,
                          actor_name=actor_name, notify=notify)

    try:
        if action == "mute":
            await mute(bot, chat_id, user_id, minutes)
            audit.count(chat_id, "mutes")
            text = _t(chat_id, "mod.muted", name=escape(user_name), minutes=minutes, reason=reason)
        elif action == "tempban":
            await tempban(bot, chat_id, user_id, minutes)
            audit.count(chat_id, "bans")
            text = _t(chat_id, "mod.tempbanned", name=escape(user_name), minutes=minutes, reason=reason)
        elif action == "ban":
            await ban(bot, chat_id, user_id)
            audit.count(chat_id, "bans")
            text = _t(chat_id, "mod.banned", name=escape(user_name), reason=reason)
        else:
            return "none"
    except ModerationError as error:
        logger.warning("PUNISH %s: %s", action, error)
        return "failed"

    audit.log(
        "moderation", action, chat_id=chat_id,
        actor_kind=actor_kind, actor_id=actor_id, actor_name=actor_name,
        target_id=user_id, target_name=user_name,
        details=(f"{minutes} мин · " if action in ("mute", "tempban") else "") + reason,
    )

    if notify:
        try:
            await notify(text)
        except Exception:
            pass

    return action


async def warn(bot, chat_id: int, user_id: int, user_name: str, reason: str,
               actor_kind: str = "bot", actor_id: int | None = None,
               actor_name: str | None = None, notify=None) -> str:
    """Предупреждение. На лимите — эскалация по правилу группы."""
    from database.repository import add_warning, clear_warnings

    total = await add_warning(chat_id, user_id, reason)
    limit = get_number(chat_id, "warn_limit") or 3

    audit.count(chat_id, "warnings")
    audit.log(
        "moderation", "warn", chat_id=chat_id,
        actor_kind=actor_kind, actor_id=actor_id, actor_name=actor_name,
        target_id=user_id, target_name=user_name,
        details=f"{total}/{limit} · {reason}",
    )

    if total >= limit:
        await clear_warnings(chat_id, user_id)

        return await apply_punishment(
            bot, chat_id, user_id, user_name,
            get_value(chat_id, "warn_action") or "mute",
            get_number(chat_id, "punish_minutes") or 60,
            _t(chat_id, "reason.warn_limit", limit=limit),
            notify=notify,
        )

    if notify:
        try:
            await notify(_t(chat_id, "mod.warned", name=escape(user_name), reason=reason, total=total, limit=limit))
        except Exception:
            pass

    return "warn"


@router.message(is_candidate)
async def punish(message: Message):
    chat_id = message.chat.id
    user = message.from_user
    name = display_name_of(user)

    violation = _verdicts.pop((chat_id, message.message_id), None) or "flood"

    if await _is_admin(message.bot, chat_id, user.id):
        return

    reason = reason_text(chat_id, violation)
    action = get_value(chat_id, ACTION_SETTINGS.get(violation, "act_flood")) or "warn"
    minutes = get_number(chat_id, "punish_minutes") or 60

    # Свои правила группы важнее действия по умолчанию
    now = time.monotonic()
    history = _history[(chat_id, user.id)]
    history.append((now, violation))

    rule = match_rule(_rules.get(chat_id, []), history, violation, now)

    if rule is not None:
        action, minutes = rule["action"], rule["duration"]
        reason = f"{reason} · {describe_rule(rule).split(' → ')[0].lower()}"

    try:
        await message.delete()
        audit.count(chat_id, "deleted")
    except Exception:
        pass

    audit.log(
        "moderation", "violation", chat_id=chat_id, actor_kind="bot",
        target_id=user.id, target_name=name, details=reason,
    )

    if action == "delete":
        return

    await apply_punishment(
        message.bot, chat_id, user.id, name, action, minutes, reason,
        notify=message.answer,
    )
