"""
Своя коллекция картинок — логика без Telegram.

Названия и хэштеги, слова-триггеры, коллекции как действия,
привязки к действиям, выбор картинки. Здесь нет aiogram, поэтому
модуль можно импортировать из поиска действий и проверять тестами.
Загрузка фото через личку — в images_library.py.
"""

import logging
import re

from settings.store import is_enabled


logger = logging.getLogger("maruska.library")


CATS = "cats"
PAIR = "pair_of_day"
PAIR_WORDS = {"пара дня", "парадня", "пара", "пары", "влюбленные", "любовь"}

CAT_WORDS = {"кошки", "кошка", "котики", "котик", "коты", "кот", "котята", "cats", "cat", "мяу"}

ALBUM_WAIT = 2.0        # секунд: Telegram присылает альбом отдельными сообщениями
TAG_MEMORY = 120        # секунд: столько помним последний хэштег для следующих пачек
REPORT_WAIT = 4.0       # секунд тишины — и Мара присылает один общий отчёт
MAX_TAG = 40


# ---------------------------------------------------------
# Чистые функции — покрыты тестами
# ---------------------------------------------------------

def normalize_tag(text: str) -> str | None:
    """«#Пиво» → «пиво», «#мои_котики» → «мои котики». Пусто — None."""
    tag = (text or "").strip().lstrip("#").replace("_", " ").lower().replace("ё", "е")
    tag = " ".join(re.sub(r"[^\w\s-]", " ", tag).split())[:MAX_TAG]
    return tag or None


def tag_from_caption(caption: str | None) -> str | None:
    """Первый хэштег из подписи: «вот #пиво холодное» → «пиво»."""
    match = re.search(r"#([\w-]+)", caption or "")
    return normalize_tag(match.group(1)) if match else None


def resolve_tag(caption_tag: str | None, last: tuple | None, now: float,
                ttl: float = TAG_MEMORY) -> str | None:
    """
    Хэштег для пачки фото. Telegram разбивает 30 фото на альбомы по 10
    и подпись ставит только к первому — остальные приходят без неё.
    Поэтому пачка без подписи берёт хэштег предыдущей, если та была
    совсем недавно.
    """
    if caption_tag:
        return caption_tag

    if last and now - last[1] <= ttl:
        return last[0]

    return None


# Фразы для коллекций-действий: предмет стоит после двоеточия,
# поэтому его не нужно склонять — «Стас отправил Кате: булочка»
LIBRARY_PHRASES = (
    "{emoji} {actor} <отправил|отправила> {target_dat}: <b>{item}</b>",
    "{emoji} {actor} <поделился|поделилась> с {target_instr}: <b>{item}</b>",
    "{emoji} Для {target_gen} от {actor_gen}: <b>{item}</b>",
    "{emoji} {target}, это тебе от {actor_gen}: <b>{item}</b>",
)


# Готовые подписи для коллекций, которые появились в группах сами.
# Ключ — основа названия коллекции: ловит «электрический стул»,
# «электрический_стул», «электростул». Своя фраза коллекции важнее.
SPECIAL_PHRASES = {
    ("электрическ", "электростул"): (
        "{emoji} {actor} <усадил|усадила> {target_acc} на электрический стул. Говорят, бодрит лучше кофе ☕",
        "{emoji} {target}, присаживайся! {actor} <оплатил|оплатила> тебе сеанс экспресс-завивки ⚡",
        "{emoji} {actor} <подключил|подключила> {target_acc} к сети. Теперь {target} заряжает телефоны прикосновением 🔌",
        "{emoji} Приговор от {actor_gen}: {target} — 220 вольт без права на розетку ⚡",
        "{emoji} {actor} <решил|решила>, что {target_dat} не хватает искры в жизни. Искра доставлена ⚡",
        "{emoji} {target}, это не кресло-массажёр. Но {actor} <сказал|сказала>, что тебе понравится 🪑",
        "{emoji} {actor} <нажал|нажала> рубильник. {target} теперь светится в темноте 💡",
        "{emoji} Электрик {actor} <проверил|проверила> проводку на {target_instr}. Проводка рабочая ⚡",
        "{emoji} Отдых у {target_gen} отменяется: {actor} <включил|включила> режим «турбо» 🔋",
        "{emoji} {actor} <отправил|отправила> {target_acc} на перезагрузку. Выключить и включить — классика 🔄",
        "{emoji} Счёт за электричество {target_gen} в этом месяце оплачивает {actor} ⚡🧾",
        "{emoji} {actor} <прописал|прописала> {target_dat} электрошоковую терапию от лени. Минус лень, плюс причёска 🦔",
        "{emoji} {target}, улыбнись! {actor} <сделал|сделала> тебе фото со вспышкой. Очень яркой вспышкой ⚡📸",
        "{emoji} {actor} <подарил|подарила> {target_dat} стул. С подогревом. Сильным подогревом 🔥",
        "{emoji} Тесла бы гордился: {actor} <провёл|провела> на {target_instr} опыт с переменным током ⚡",
        "{emoji} {target} теперь официально энергетик. Спасибо {actor_dat} за подключение 🔋",
        "{emoji} {actor} <зарядил|зарядила> {target_acc} на 100%. Хватит на неделю без сна ⚡",
        "{emoji} {target}, хватит спорить в чате. {actor} <выписал|выписала> 380 вольт аргументов ⚡",
        "{emoji} «Садись, в ногах правды нет», — <сказал|сказала> {actor} и <щёлкнул|щёлкнула> выключателем 🪑⚡",
        "{emoji} {actor} <устроил|устроила> {target_dat} ускоренный курс физики. Тема урока: закон Ома ⚡📚",
        "{emoji} У {target_gen} волосы дыбом, а у {actor_gen} — довольная улыбка ⚡😏",
        "{emoji} {target} больше не тормозит: {actor} <разогнал|разогнала> до скорости тока ⚡",
        "{emoji} {actor} <проверил|проверила>, работает ли у {target_gen} мозг. Искрит — значит, работает 🧠⚡",
        "{emoji} Сеанс шоковой терапии от {actor_gen}. {target}, это для твоего же блага 💆⚡",
        "{emoji} {actor} <нашёл|нашла> у {target_gen} кнопку «вкл». Пользуйтесь, пока горячо ⚡",
        "{emoji} {target}, поздравляем! Ты — самый заряженный участник чата. Номинация от {actor_gen} 🏆⚡",
    ),
    ("ловелас", "бабник"): (
        "{emoji} {actor} <рассекретил|рассекретила> {target_acc}: в телефоне 47 контактов «Солнышко» и ни одного «Мама» 📱",
        "{emoji} {target}, {actor} всё <видел|видела>: три подмигивания за минуту, и одно — официантке 😉",
        "{emoji} Внимание, чат! {actor} <объявил|объявила> {target_acc} официальным ловеласом района 🏆",
        "{emoji} {actor} <вручил|вручила> {target_dat} диплом «Кандидат наук по подкатам» 🎓💋",
        "{emoji} {target} пишет «ты особенная» всем подряд. Копировать-вставить, {actor} <проверил|проверила> 📋",
        "{emoji} {actor} <завёл|завела> на {target_acc} досье. Толще, чем «Война и мир» 📚",
        "{emoji} У {target_gen} в календаре свиданий больше, чем рабочих дней. Источник — {actor} 📅",
        "{emoji} {actor} <поставил|поставила> {target_dat} памятник: «Здесь был тот, кто знал все пароли от сердец» 🗿❤️",
        "{emoji} {target}, Казанова звонил — просит вернуть методичку. Передаёт {actor} ☎️",
        "{emoji} {actor} <выдал|выдала> {target_dat} абонемент в цветочный: оптом дешевле 🌹🌹🌹",
        "{emoji} Тиндер прислал {target_dat} письмо: «Притормози, сервер не вывозит». <Переслал|Переслала> {actor} 📩",
        "{emoji} {actor} <подсчитал|подсчитала>: {target} влюбляется в среднем раз в 15 минут ⏱",
        "{emoji} {target}, у тебя не сердце, а гостиница: заезд в 14:00, выезд в 12:00. Отзыв от {actor_gen} 🏨",
        "{emoji} {actor} <поймал|поймала> {target_acc} на фразе «такого со мной ещё не было». Пятый раз за неделю 🙄",
        "{emoji} {target} получает звание «Сердцеед года». Решающий голос — от {actor_gen} 🗳",
        "{emoji} {actor} <нашёл|нашла> у {target_gen} в заметках таблицу «кому что обещано». Таблица на 3 листа 📊",
        "{emoji} Комплименты {target_gen} опасны для здоровья: {actor} уже <покраснел|покраснела> 😳",
        "{emoji} {target}, сколько можно разбивать сердца? {actor} уже склеивает осколки скотчем 💔🩹",
        "{emoji} {actor} <предупредил|предупредила> чат: {target} подкатывает даже к кофемашине ☕😏",
        "{emoji} {target} — это когда «мы просто друзья», а у друзей уже ревность. Диагноз от {actor_gen} 🩺",
        "{emoji} {actor} <оформил|оформила> {target_dat} лицензию на флирт. Без лимита, с продлением 📜",
        "{emoji} У {target_gen} столько бывших, что на встречу выпускников снимают зал. Организатор — {actor} 🎉",
        "{emoji} {target}, Дон Жуан в ученики просится. {actor} <передал|передала> резюме 📝",
        "{emoji} {actor} <разоблачил|разоблачила>: у {target_gen} одна песня «для неё» — на всех 🎸",
        "{emoji} Осторожно, {target} в чате! {actor} <раздал|раздала> всем зонтики от чар ☂️",
        "{emoji} {actor} <спросил|спросила> {target_acc}, кого любишь. Ответ «всех» засчитан как честный 😅",
    ),
}


def special_phrases(tag: str) -> tuple | None:
    clean = (normalize_tag(tag) or "").replace(" ", "")
    for bases, phrases in SPECIAL_PHRASES.items():
        if any(clean.startswith(base) for base in bases):
            return phrases
    return None


def stem(word: str) -> str:
    """«булочка» → «булочк»: ловит «булочку», «булочки», «булочкой»."""
    word = normalize_tag(word) or ""
    if " " in word or len(word) < 5:
        return word
    return re.sub(r"[аяоеиыуюь]$", "", word) or word


def trigger_matches(text: str, triggers: list[str]) -> bool:
    """
    Короткое сообщение (до 3 слов), которое начинается со слова-триггера
    в любой форме. Длинные фразы не считаются — иначе действие
    срабатывало бы посреди разговора.
    """
    clean = normalize_tag(re.sub(r"@\w+", " ", text or "")) or ""

    if not clean or len(clean.split()) > 3:
        return False

    for trigger in triggers:
        base = stem(trigger)
        if base and (clean == normalize_tag(trigger) or clean.startswith(base)):
            return True

    return False


def guess_target(tag: str) -> str | None:
    """К чему привязать коллекцию автоматически."""
    if tag in CAT_WORDS:
        return CATS

    if tag in PAIR_WORDS:
        return PAIR

    from actions.catalog import find_action

    action = find_action(tag)
    return action.key if action else None


# ---------------------------------------------------------
# Привязки: коллекция ↔ действие
# ---------------------------------------------------------

_tags_for: dict[str, list[str]] = {}     # действие/cats → коллекции
_collections: dict[str, dict] = {}       # тег → настройки коллекции-действия


def prime_links(pairs) -> None:
    result: dict[str, list[str]] = {}
    for tag, target in pairs:
        result.setdefault(target, []).append(tag)
    _tags_for.clear()
    _tags_for.update(result)


async def reload_links() -> None:
    from database.repository import all_library_links

    prime_links(await all_library_links())


def tags_for(target: str) -> list[str]:
    # Своё действие коллекции: ключ «lib:булочка» → коллекция «булочка»
    if target.startswith("lib:"):
        return [target[4:]]
    return _tags_for.get(target, [])


def prime_collections(rows) -> None:
    _collections.clear()
    for row in rows:
        _collections[row.tag] = {
            "emoji": row.emoji or "✨",
            "as_action": bool(row.as_action),
            "triggers": list(row.triggers or []),
            "phrase": row.phrase,
        }


async def reload_collections() -> None:
    from database.repository import list_library_collections

    prime_collections(await list_library_collections())


def action_for(tag: str):
    """Коллекция в виде действия — тем же объектом, что и встроенные."""
    from actions.catalog_data import Action

    meta = _collections.get(tag, {})

    return Action(
        key=f"lib:{tag}",
        emoji=meta.get("emoji") or "✨",
        search=tag,
        aliases=tuple([tag] + meta.get("triggers", [])),
        category="library",
        item_acc=tag,
        item_instr=tag,
    )


def find_collection_action(text: str):
    """Своё действие по тексту сообщения — или None."""
    for tag, meta in _collections.items():
        if meta.get("as_action") and trigger_matches(text, [tag] + meta.get("triggers", [])):
            return action_for(tag)
    return None


def phrases_for(action) -> tuple:
    tag = action.key[4:] if action.key.startswith("lib:") else action.key
    own = (_collections.get(tag) or {}).get("phrase")
    if own:
        return (own,)
    return special_phrases(tag) or LIBRARY_PHRASES


async def pick(chat_id: int | None, target: str) -> dict | None:
    """Картинка из своих коллекций для действия — или None."""
    if chat_id is not None and chat_id < 0 and not is_enabled(chat_id, "library"):
        return None

    tags = tags_for(target)

    if not tags:
        return None

    from database.repository import pick_library_image

    try:
        return await pick_library_image(tags)
    except Exception as error:
        logger.error("LIBRARY PICK: %s %s", type(error).__name__, error)
        return None
