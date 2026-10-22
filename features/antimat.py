"""
Антимат.

Два источника слов:
  • умный словарь Мары (настройка «Умный словарь», по умолчанию включён) — корни
    русского мата со всеми формами и приставками: «нахуй», «заебал», «распиздяй»,
    «выблядок», «долбоёб», «хер», «манда», «залупа» — и с исключениями для обычных
    слов («себе», «сабля», «команда», «мандарин», «хулиган», «сухую», «вебинар»);
  • свой список админа в панели:
        сука     — только это слово целиком
        хуй*     — слова, начинающиеся с «хуй» (и с приставками: «нахуй», «захуярить»)
        *пизд*   — «пизд» в любом месте слова

Мат ловится и в маскировке:
  • латиница и цифры вместо кириллицы («xуй», «cyka», «п1зда», «3аебал», «6ля»),
    украинские буквы («пiзда»), «стильные» шрифты и широкие буквы («𝐱уй», «ｈуй»);
  • транслит латиницей («huy», «pizda», «blyat», «nahuy»);
  • звёздочки и решётки вместо букв («х*й», «бл@ть», «п**да», «еб#ть»);
  • растянутые буквы («хууууй»), буквы через точку, пробел, дефис или смайлик
    («х.у.й», «х у й», «х🙂у🙂й»), слово, разорванное пробелом («ху йня»);
  • невидимые символы и ударения внутри слова.
Слова из списка «Исключения» не трогаются никогда.

За каждый мат Мара удаляет сообщение и делает предупреждение («1/3», «2/3», «3/3»);
предупреждение само исчезает через заданное время, чтобы не засорять чат. Если
указан срок мута, на последнем предупреждении человек получает мут, и счёт
начинается заново; при «Удваивать мут» каждый следующий мут за 30 дней вдвое
длиннее (до 7 дней). Отредактированные сообщения проверяются так же — мат нельзя
дописать правкой. Админов — по настройке «Наказывать и админов» (мут админу
Telegram не позволяет: им только предупреждения). Сообщения через инлайн-бота
(подпись «via @бот») не трогаем: текст выбрал бот.
"""

import asyncio
import itertools
import logging
import re
import time
import unicodedata
from html import escape

from aiogram import Router
from aiogram.types import Message

import audit
from botcontext import display_name_of
from settings.store import get_number, get_text, is_enabled

logger = logging.getLogger("maruska.antimat")

router = Router(name="antimat")

# Причина предупреждения — по ней антимат считает только свои предупреждения
REASON = "Мат"
# Каждый мут за мат — тоже запись: по ним следующий мут удваивается
MUTE_REASON = "Мат: мут"
MAX_MUTE_MINUTES = 7 * 1440

from settings.registry import ANTIMAT_DEFAULT_WORDS as DEFAULT_WORDS  # noqa: E402,F401

# Похожие латинские, украинские буквы и цифры → кириллица
LOOKALIKE = str.maketrans({
    "a": "а", "b": "в", "c": "с", "e": "е", "h": "н", "k": "к", "m": "м", "o": "о",
    "p": "р", "t": "т", "x": "х", "y": "у", "u": "и", "i": "и", "3": "з", "0": "о",
    "6": "б", "1": "и", "4": "ч", "@": "а", "$": "с", "ё": "е", "і": "и", "ї": "и",
    "є": "е", "ґ": "г",
})

# Второе прочтение латиницы внутри русского слова: «hуй» — это «хуй», «nизда» — «пизда»
LOOKALIKE_ALT = str.maketrans({"h": "х", "n": "п", "r": "г", "w": "ш"})

# Транслит латиницей: «huy», «pizda», «blyat», «nahuy»
_TRANSLIT_PAIRS = (
    ("shch", "щ"), ("sch", "щ"), ("sh", "ш"), ("ch", "ч"), ("zh", "ж"), ("kh", "х"),
    ("ya", "я"), ("ja", "я"), ("yu", "ю"), ("ju", "ю"), ("yo", "е"), ("jo", "е"),
    ("ye", "е"), ("ts", "ц"),
)
_TRANSLIT_ONE = str.maketrans({
    "a": "а", "b": "б", "v": "в", "w": "в", "g": "г", "d": "д", "e": "е", "z": "з",
    "i": "и", "j": "й", "k": "к", "q": "к", "c": "к", "l": "л", "m": "м", "n": "н",
    "o": "о", "p": "п", "r": "р", "s": "с", "t": "т", "u": "у", "f": "ф", "h": "х",
    "x": "х",
})
# Английские слова, которые в транслите похожи на мат
_LATIN_SAFE = {"hue", "hues", "huey", "ebay", "huevo", "huevos", "her", "hers", "other", "others", "ebullient"}
# По этим сочетаниям видно английское слово, а не мат транслитом («other», «web», «queen», «look»)
_ENGLISH = re.compile(r"th|w|q|ee|oo|ou|ea")

# Приставки, с которыми мат начинается не с корня: «на-хуй», «за-ебал», «вы-блядок»
PREFIXES = (
    "", "на", "за", "вы", "по", "у", "от", "до", "об", "о", "раз", "рас", "при", "про",
    "пере", "недо", "под", "из", "вз", "с", "съ", "в", "под", "долбо", "ни", "ах",
)
_PREFIX = r"(?:не|ни|на|за|вы|по|о|об|обо|объ|от|ото|отъ|до|раз|рас|разъ|при|про|пре|пере|недо|под|подъ|из|изъ|вз|въ|с|съ|у|в|долбо|полу|вс)"

# Умный словарь: корни мата со всеми формами (токен уже нормализован: ё→е, повторы схлопнуты)
_BUILTIN = [re.compile(p) for p in (
    rf"^{_PREFIX}{{0,3}}ху[йяеию]",
    r"^хули$",
    r"пизд",
    rf"^{_PREFIX}{{0,3}}бля(?:[дт]|$)",
    rf"^{_PREFIX}{{0,3}}еб(?:[аеиклнуы]|ть|$)",
    r"^сук(?:а|и|е|у|ой|ою|ам|ами|ах|ин|ина|ины|ину|ой)$",
    r"^суч(?:ка|ке|ку|кой|ара|ары|аре|ару|арой|ий|ьего|ьей|онок)$",
    r"^муд(?:ак|ач|ил|оз|охн|офел|ень|ня)",
    r"^пид(?:ор|ар|р)",
    r"^г[ао]ндон",
    r"шлюх",
    rf"^{_PREFIX}{{0,2}}залуп",
    r"^манд(?:а|ы|е|у|ой|ою|ец|ища|ище|ей|ам|ами|ах)$",
    r"^манд(?:авош|ятин|юк)",
    rf"^{_PREFIX}{{0,2}}дроч",
    r"^(?:на|по|ни|до|за|от|вы|с|о|об|рас|рас)?хер(?:$|а|у(?!в)|ь|ом|ов|н|ач|ит|ов)",
)]
# Обычные слова, похожие на мат: «себе», «вебинар», «Ебург», «сухую»
_BUILTIN_SAFE = re.compile(
    rf"^{_PREFIX}{{0,2}}(?:сух[уи]|глух|страх|психу)|^(?:себе|веб|ебург|оскорбл|употребл|корабл|сабл)"
)

_WORD = re.compile(r"[а-яa-z0-9@$ёіїєґ*#%]+", re.IGNORECASE)
_MASK = re.compile(r"[*#%]")
# «@» читается и как «а» («бл@ть» → «блать»), и как пропущенная буква («бл@ть» → «блять»)
_UNMASK = re.compile(r"[*#%@]")
# Буквы, разделённые точками, пробелами, звёздочками, дефисами, смайликами: «х.у.й», «х у й», «х🙂у🙂й»
_SPACED = re.compile(r"(?:(?<![а-яa-zё])[а-яa-zё](?:[^\wа-яё]|_){1,3}){2,}[а-яa-zё](?![а-яa-zё])", re.IGNORECASE)
# Отдельные короткие слова, после которых пробел — настоящий («в хлеб», «на небо»)
_STANDALONE = {
    "а", "и", "в", "к", "с", "у", "о", "я", "ж", "б", "ну", "на", "по", "за", "от", "до", "из",
    "не", "ни", "но", "же", "ли", "бы", "то", "мы", "вы", "он", "ты", "да", "ей", "им", "их",
    "уж", "во", "со", "ко", "об", "ой", "ах", "ох", "эх", "ух", "ее", "её", "ок", "мне", "все",
}
_INVISIBLE = re.compile(r"[\u00ad\u200b-\u200f\u2060-\u2064\ufeff\u034f\u180e]")
# Какие буквы прячут под звёздочкой: гласные и согласные из корней мата («х*й», «п**да», «бл*ть»)
_LETTERS = "аеиоуыяюйзлбдн"
# Сколько слов со звёздочками разбирать в одном сообщении (защита от тормозов на спаме)
_MASKED_WORDS = 20

_cooldown: dict[tuple[int, int], float] = {}
_admin_cache: dict[tuple[int, int], tuple[float, bool]] = {}
_tasks: set[asyncio.Task] = set()


def clean_text(text: str) -> str:
    """Стильные шрифты → обычные буквы; без невидимых символов и ударений (но «й» и «ё» целы)."""
    text = unicodedata.normalize("NFKC", text or "")
    text = _INVISIBLE.sub("", text)
    text = "".join(ch for ch in unicodedata.normalize("NFD", text)
                   if not unicodedata.combining(ch) or ch in "\u0306\u0308")
    return unicodedata.normalize("NFC", text)


def normalize(word: str) -> str:
    """«XYЙ», «хууууй», «xуй» → «хуй»."""
    word = word.lower().translate(LOOKALIKE)
    word = re.sub(r"[^а-я]", "", word)
    # Растянутые буквы: «хуууй» → «хуй»
    return re.sub(r"(.)\1+", r"\1", word)


def translit(word: str) -> str:
    """«pizda» → «пизда»; только для слов латиницей."""
    word = word.lower()
    for latin, cyr in _TRANSLIT_PAIRS:
        word = word.replace(latin, cyr)
    # «y» после гласной — «й» («huy»), иначе «ы»
    word = re.sub(r"(?<=[аеиоуыэюя])y", "й", word.translate(_TRANSLIT_ONE)).replace("y", "ы")
    return re.sub(r"(.)\1+", r"\1", re.sub(r"[^а-я]", "", word))


def parse_words(raw: str) -> list[str]:
    """Список из панели: через запятую или с новой строки. Звёздочки сохраняются."""
    items = []
    for part in re.split(r"[,\n;]+", raw or ""):
        part = part.strip().lower()
        if not part:
            continue
        head = part.startswith("*")
        tail = part.endswith("*")
        core = normalize(part.strip("*"))
        if len(core) >= 2:
            items.append(("*" if head else "") + core + ("*" if tail else ""))
    return items


def _matches(word: str, entry: str) -> bool:
    if entry.startswith("*") and entry.endswith("*"):
        return entry[1:-1] in word
    if entry.endswith("*"):
        root = entry[:-1]
        return any(word.startswith(p + root) for p in PREFIXES)
    if entry.startswith("*"):
        return word.endswith(entry[1:])
    return word == entry


def is_builtin_swear(word: str) -> bool:
    if not word or _BUILTIN_SAFE.match(word):
        return False
    return any(p.search(word) for p in _BUILTIN)


def _unmask(word: str) -> list[str]:
    """«х*й», «п**да», «бл#ть» → варианты с буквами вместо звёздочек (не больше двух пропусков)."""
    lowered = word.lower()
    letters = _UNMASK.sub("", lowered)
    if not _UNMASK.search(lowered) or not letters or len(word) > 20:
        return []
    # Звёздочки по краям слова — оформление («**жирный**»), а не пропуск буквы
    core = lowered.strip("*#%@")
    if not _UNMASK.search(core):
        core = lowered.lstrip("*#%@")
        if not _UNMASK.search(core) or len(_UNMASK.sub("", core)) < 1:
            return []
    runs = [m for m in re.finditer(r"[*#%@]+", core)]
    if len(runs) > 2:
        return []
    found = []
    # Каждая серия звёздочек — одна или две буквы
    for sizes in itertools.product(*[(1, 2) if len(r.group(0)) > 1 else (1,) for r in runs]):
        # Не больше двух угаданных букв на слово: дальше это уже не мат, а шифровка
        if sum(sizes) > 2:
            continue
        for fill in itertools.product(_LETTERS, repeat=sum(sizes)):
            out, pos, k = [], 0, 0
            for run, size in zip(runs, sizes):
                out.append(core[pos:run.start()])
                out.append("".join(fill[k:k + size]))
                k += size
                pos = run.end()
            out.append(core[pos:])
            found.append(normalize("".join(out)))
    return found


def tokens(text: str) -> list[str]:
    """Все слова текста во всех прочтениях: как есть, латиница/цифры как кириллица, транслит, склейки."""
    text = clean_text(text)
    raw = _WORD.findall(text)
    found = []
    plain = []
    for word in raw:
        letters = _MASK.sub("", word)
        norm = normalize(letters)
        if norm:
            found.append(norm)
        # Латиница вперемешку с кириллицей: «hуй», «nизда»
        if re.search(r"[a-z]", letters, re.IGNORECASE) and re.search(r"[а-яё]", letters, re.IGNORECASE):
            alt = normalize(letters.lower().translate(LOOKALIKE_ALT))
            if alt and alt != norm:
                found.append(alt)
        # Для склейки «ху йня» — только настоящие русские обрывки, не служебные слова латиницей
        plain.append(norm if re.fullmatch(r"[а-яё]+", word, re.IGNORECASE) else "")
        latin = word.lower()
        if re.fullmatch(r"[a-z]{3,}", latin) and latin not in _LATIN_SAFE and not _ENGLISH.search(latin):
            found.append(translit(latin))
    # «х.у.й», «х у й», «х🙂у🙂й» — склеиваем буквы
    found += [normalize(m.group(0)) for m in _SPACED.finditer(text)]
    # «ху йня», «бл ять» — короткий обрывок, который сам по себе не слово, склеиваем со следующим
    for first, second in zip(plain, plain[1:]):
        if first and second and 2 <= len(first) <= 3 and first not in _STANDALONE:
            found.append(first + second)
    return [w for w in found if w]


def _masked(text: str) -> list[list[str]]:
    words = [word for word in _WORD.findall(clean_text(text)) if _UNMASK.search(word)]
    return [variants for word in words[:_MASKED_WORDS] if (variants := _unmask(word))]


def find_swear(text: str, words: list[str], builtin: bool = False, allow: list[str] | None = None) -> str | None:
    """Первое запрещённое слово в тексте или None.

    words — свой список админа, builtin — ещё и умный словарь Мары, allow — исключения."""
    if not words and not builtin:
        return None
    allow = allow or []

    def bad(token: str) -> bool:
        if any(_matches(token, entry) for entry in allow):
            return False
        return (builtin and is_builtin_swear(token)) or any(_matches(token, entry) for entry in words)

    for token in tokens(text):
        if bad(token):
            return token
    for variants in _masked(text):
        for token in variants:
            if bad(token):
                return token
    return None


def _words(chat_id: int) -> list[str]:
    return parse_words(get_text(chat_id, "antimat_words"))


def chat_swear(chat_id: int, text: str) -> str | None:
    """Мат в тексте по настройкам этой группы: умный словарь, свой список, исключения."""
    return find_swear(
        text, _words(chat_id),
        builtin=is_enabled(chat_id, "antimat_builtin"),
        allow=parse_words(get_text(chat_id, "antimat_allow")),
    )


def is_swearing(message: Message) -> bool:
    if message.chat.type not in ("group", "supergroup"):
        return False
    if message.from_user is None or message.from_user.is_bot:
        return False
    # Текст через инлайн-бота («@бот предсказание») пишет бот, а не человек
    if message.via_bot is not None:
        return False
    if not is_enabled(message.chat.id, "antimat"):
        return False
    return chat_swear(message.chat.id, message_text(message)) is not None


def message_text(message: Message) -> str:
    """Всё, что человек написал: текст или подпись, а в опросе — вопрос и варианты."""
    parts = [message.text or message.caption or ""]
    poll = getattr(message, "poll", None)
    if poll is not None:
        parts.append(poll.question or "")
        parts += [option.text or "" for option in poll.options or []]
    return "\n".join(p for p in parts if p)


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


async def _delete_later(message, delay: int) -> None:
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except Exception:
        pass


async def _notice(message: Message, text: str) -> None:
    """Предупреждение Мары: через antimat_notice_seconds оно само исчезает (0 — остаётся)."""
    sent = await message.answer(text)
    seconds = get_number(message.chat.id, "antimat_notice_seconds")
    if sent is not None and seconds > 0:
        task = asyncio.create_task(_delete_later(sent, seconds))
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)


def mute_minutes(base: int, earlier_mutes: int, escalate: bool) -> int:
    """Срок мута: каждый следующий за 30 дней вдвое длиннее, но не больше 7 дней."""
    if base <= 0:
        return 0
    if not escalate:
        return base
    return min(base * 2 ** min(earlier_mutes, 10), max(base, MAX_MUTE_MINUTES))


@router.edited_message(is_swearing)
@router.message(is_swearing)
async def on_swear(message: Message):
    from database.repository import add_warning, clear_warnings_by_reason, count_warnings_by_reason
    from features.moderation import ModerationError, mute

    chat_id = message.chat.id
    user = message.from_user
    name = display_name_of(user)

    admin = await _is_admin(message.bot, chat_id, user.id)
    if admin and not is_enabled(chat_id, "antimat_admins"):
        return

    if is_enabled(chat_id, "antimat_delete"):
        try:
            await message.delete()
            audit.count(chat_id, "deleted")
        except Exception:
            pass

    # Несколько сообщений подряд за пару секунд — одно предупреждение, не три
    now = time.monotonic()
    key = (chat_id, user.id)
    if now - _cooldown.get(key, 0) < 3:
        return
    _cooldown[key] = now
    if len(_cooldown) > 5000:
        _cooldown.clear()

    limit = max(1, get_number(chat_id, "antimat_warnings") or 3)
    minutes = get_number(chat_id, "antimat_mute_minutes") or 0

    await add_warning(chat_id, user.id, REASON)
    total = await count_warnings_by_reason(chat_id, user.id, REASON)
    audit.count(chat_id, "warnings")
    audit.log(
        "moderation", "warn", chat_id=chat_id, actor_kind="bot",
        target_id=user.id, target_name=name, details=f"{min(total, limit)}/{limit} · мат",
    )

    who = f'<a href="tg://user?id={user.id}">{escape(name)}</a>'

    if total < limit:
        await _notice(message, f"🤬 {who}, без мата! Предупреждение {total}/{limit}.")
        return

    # Последнее предупреждение: мут, если админ указал срок; счёт заново
    await clear_warnings_by_reason(chat_id, user.id, REASON)

    if minutes <= 0:
        await _notice(message, f"🤬 {who}, без мата! Предупреждение {limit}/{limit}. Следующий раз счёт начнётся заново.")
        return

    # Повторный мут за 30 дней — вдвое длиннее
    earlier = await count_warnings_by_reason(chat_id, user.id, MUTE_REASON)
    base = minutes
    minutes = mute_minutes(base, earlier, is_enabled(chat_id, "antimat_escalate"))

    try:
        await mute(message.bot, chat_id, user.id, minutes)
    except ModerationError as error:
        logger.warning("ANTIMAT mute: %s", error)
        why = ("Telegram не даёт ограничивать администраторов — только предупреждение."
               if admin else f"Замутить не получилось: {error}")
        await _notice(message, f"🤬 {who}, без мата! Предупреждение {limit}/{limit}. {why}")
        return

    await add_warning(chat_id, user.id, MUTE_REASON)
    audit.count(chat_id, "mutes")
    audit.log(
        "moderation", "mute", chat_id=chat_id, actor_kind="bot",
        target_id=user.id, target_name=name, details=f"{minutes} мин · мат, {limit} предупреждения",
    )
    again = f" Это уже {earlier + 1}-й мут за месяц — срок вдвое длиннее прошлого." if minutes > base else ""
    await message.answer(f"🔇 {who} получает мут на {_duration(minutes)} — {limit} предупреждения за мат.{again}")


def _duration(minutes: int) -> str:
    if minutes % 1440 == 0:
        days = minutes // 1440
        return f"{days} д"
    if minutes % 60 == 0:
        return f"{minutes // 60} ч"
    return f"{minutes} мин"
