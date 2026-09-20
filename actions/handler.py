import re
from html import escape

from aiogram import Router
from aiogram.types import Message

from actions.catalog import find_action
from actions.service import get_image_for_action, IMAGE_VERSION
from database.repository import save_user, save_message, get_user_by_username, infer_gender

router = Router()


def get_display_name(user) -> str:
    return user.first_name or user.username or "Пользователь"


def get_gender(user) -> str:
    return infer_gender(get_display_name(user))


def pair_key(actor_gender: str, target_gender: str) -> str:
    if {actor_gender, target_gender} == {"male", "female"}:
        return "male_female"
    if actor_gender == "male" and target_gender == "male":
        return "male_male"
    if actor_gender == "female" and target_gender == "female":
        return "female_female"
    return "neutral"


MALE_NAMES = {"стас", "станислав", "иван", "андрей", "александр", "сергей", "дмитрий", "максим", "михаил", "николай", "евгений", "роман", "артем", "артём", "алексей", "владимир", "виктор", "павел", "денис", "антон", "илья", "никита", "лука", "федор", "фёдор", "олег", "игорь", "василий", "юрий", "богдан", "ярослав", "матвей", "тимур", "глеб", "лев", "марк", "петр", "пётр", "саша", "женя", "валера", "миша", "дима", "серёжа", "сережа", "лёша", "леша", "паша", "вова"}


def to_accusative(name: str, gender: str = "unknown") -> str:
    clean = name.strip()
    lower = clean.lower()
    if not re.search(r"[а-яё]", lower) or gender == "unknown":
        return clean
    if gender == "female":
        if lower.endswith("ия"): return clean[:-2] + "ию"
        if lower.endswith("я"): return clean[:-1] + "ю"
        if lower.endswith("а"): return clean[:-1] + "у"
        if lower.endswith("ь"): return clean
        return clean
    if lower.endswith("й"): return clean[:-1] + "я"
    if lower.endswith("я"): return clean[:-1] + "ю"
    if lower.endswith("ь"): return clean[:-1] + "я"
    if lower.endswith("а") and lower in MALE_NAMES: return clean[:-1] + "у"
    return clean + "а"


def to_dative(name: str, gender: str = "unknown") -> str:
    clean = name.strip(); lower = clean.lower()
    if not re.search(r"[а-яё]", lower) or gender == "unknown": return clean
    if gender == "female":
        if lower.endswith("ия"): return clean[:-2] + "ии"
        if lower.endswith("я"): return clean[:-1] + "е"
        if lower.endswith("а"): return clean[:-1] + "е"
        if lower.endswith("ь"): return clean + "и"
        return clean
    if lower.endswith("й"): return clean[:-1] + "ю"
    if lower.endswith("ь"): return clean[:-1] + "ю"
    if lower.endswith("я"): return clean[:-1] + "е"
    if lower.endswith("а") and lower in MALE_NAMES: return clean[:-1] + "е"
    return clean + "у"


def to_instrumental(name: str, gender: str = "unknown") -> str:
    clean = name.strip(); lower = clean.lower()
    if not re.search(r"[а-яё]", lower) or gender == "unknown": return clean
    if gender == "female":
        if lower.endswith("ия"): return clean[:-2] + "ией"
        if lower.endswith("я"): return clean[:-1] + "ей"
        if lower.endswith("а"): return clean[:-1] + "ой"
        if lower.endswith("ь"): return clean + "ью"
        return clean
    if lower.endswith("й"): return clean[:-1] + "ем"
    if lower.endswith("я"): return clean[:-1] + "ей"
    if lower.endswith("ь"): return clean[:-1] + "ем"
    if lower.endswith("а") and lower in MALE_NAMES: return clean[:-1] + "ой"
    return clean + "ом"


def actor_form(gender: str, male: str, female: str, unknown: str | None = None) -> str:
    return male if gender == "male" else female if gender == "female" else (unknown or f"{male}(а)")


def _drink_verb(text: str) -> str:
    t = text.lower()
    if any(x in t for x in ("угости", "угост", "угощ")): return "treat"
    if any(x in t for x in ("напои", "напо", "поить", "пою")): return "pour"
    return "together"


def _food_verb(text: str) -> str:
    t = text.lower()
    if any(x in t for x in ("накорм", "корми", "покорм")): return "feed"
    return "treat"


def build_action_text(message_text: str, actor_name: str, target_name: str, action, actor_gender: str = "unknown", target_gender: str = "unknown") -> str:
    actor = escape(actor_name)
    target_acc = escape(to_accusative(target_name, target_gender))
    target_dat = escape(to_dative(target_name, target_gender))
    target_instr = escape(to_instrumental(target_name, target_gender))

    if action.category == "drink":
        verb = _drink_verb(message_text)
        if verb == "treat":
            v = actor_form(actor_gender, "угостил", "угостила")
            return f"{action.emoji} <b>{actor}</b> {v} <b>{target_acc}</b> {action.item_instr} ♡"
        if verb == "pour":
            v = actor_form(actor_gender, "напоил", "напоили")
            return f"{action.emoji} <b>{actor}</b> {v} <b>{target_acc}</b> {action.item_instr} ♡"
        v = actor_form(actor_gender, "выпил", "выпила")
        return f"{action.emoji} <b>{actor}</b> {v} {action.item_acc} вместе с <b>{target_instr}</b> ♡"

    if action.category == "food":
        v = actor_form(actor_gender, "накормил", "накормила") if _food_verb(message_text) == "feed" else actor_form(actor_gender, "угостил", "угостила")
        return f"{action.emoji} <b>{actor}</b> {v} <b>{target_acc}</b> {action.item_instr} ♡"

    if action.category in ("flower", "gift"):
        v = actor_form(actor_gender, "подарил", "подарила")
        return f"{action.emoji} <b>{actor}</b> {v} <b>{target_dat}</b> {action.item_acc} ♡"

    forms = {
        "hug": ("обнял", "обняла", f"<b>{target_acc}</b>"),
        "kiss": ("поцеловал", "поцеловала", f"<b>{target_acc}</b>"),
        "highfive": ("дал", "дала", f"пять <b>{target_dat}</b>"),
        "handshake": ("пожал", "пожала", f"руку <b>{target_acc}</b>"),
        "support": ("поддержал", "поддержала", f"<b>{target_acc}</b>"),
        "congratulations": ("поздравил", "поздравила", f"<b>{target_acc}</b>"),
        "party": ("потусовался", "потусовалась", f"вместе с <b>{target_instr}</b>"),
        "movie": ("посмотрел", "посмотрела", f"кино вместе с <b>{target_instr}</b>"),
        "music": ("послушал", "послушала", f"музыку вместе с <b>{target_instr}</b>"),
        "dance": ("потанцевал", "потанцевала", f"с <b>{target_instr}</b>"),
    }
    if action.key in forms:
        male, female, tail = forms[action.key]
        return f"{action.emoji} <b>{actor}</b> {actor_form(actor_gender, male, female)} {tail} ♡"
    return f"{action.emoji} <b>{actor}</b> сделал(а) что-то вместе с <b>{target_instr}</b> ♡"


async def find_target(message: Message):
    if message.reply_to_message:
        target = message.reply_to_message.from_user
        if target is not None and not target.is_bot:
            return target
    match = re.search(r"@([A-Za-z0-9_]{3,32})", message.text or "")
    if match:
        return await get_user_by_username(match.group(1))
    return None


@router.message()
async def action_handler(message: Message):
    if message.chat.type not in ("group", "supergroup") or not message.from_user or message.from_user.is_bot or not message.text:
        return
    action = find_action(message.text)
    if action is None:
        return
    target = await find_target(message)
    if target is None or target.id == message.from_user.id:
        return

    await save_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    await save_user(target.id, target.username, target.first_name)
    await save_message(message.chat.id, message.from_user.id, message.from_user.first_name or message.from_user.username, message.text)

    actor_gender = get_gender(message.from_user)
    target_gender = get_gender(target)
    pair = pair_key(actor_gender, target_gender) if action.category == "pair" else "neutral"
    image_key = f"{action.key}:{pair}:{IMAGE_VERSION}" if action.category == "pair" else f"{action.key}:{IMAGE_VERSION}"

    try:
        image = await get_image_for_action(action, image_key=image_key, pair_key=pair)
    except Exception as error:
        print("ACTION IMAGE ERROR:", type(error).__name__, str(error))
        await message.reply("Не смогла найти картинку 😔")
        return
    if image is None:
        await message.reply("Для этого действия пока нет подходящей картинки 😔")
        return

    caption = build_action_text(message.text, get_display_name(message.from_user), get_display_name(target), action, actor_gender, target_gender)
    attribution = (
        "\n\n"
        f"📷 <a href=\"{escape(image.photographer_url)}\">Фото: {escape(image.photographer_name)}</a> · "
        f"<a href=\"{escape(image.unsplash_url)}\">Unsplash</a>"
    )
    try:
        await message.bot.send_photo(chat_id=message.chat.id, photo=image.image_url, caption=caption + attribution, parse_mode="HTML")
    except Exception as error:
        print("TELEGRAM PHOTO ERROR:", type(error).__name__, str(error))
        from database.repository import release_action_image
        await release_action_image(image.id)
        await message.reply("Не получилось отправить фотографию 😔")
