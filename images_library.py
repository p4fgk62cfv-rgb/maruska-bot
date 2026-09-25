"""
Своя коллекция картинок.

Как пополнять: владелец бота кидает Маре в личку фото или альбом
с подписью «#пиво» — всё улетает в коллекцию «пиво». Фото хранятся
в самом Telegram (запоминается только file_id), поэтому ни хостинга,
ни места в базе, ни лимитов.

Коллекция привязывается к действию («пиво» → 🍺) или к котикам
(«кошки» → «Мара, мяу» и «покажи меня»). При загрузке привязка
ставится сама, если по названию понятно, о чём речь; остальное —
в панели.

Бот берёт картинку из своей коллекции первой, а если своих нет —
из Pixabay, как раньше.
"""

import asyncio
import logging
import re

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

import audit

from settings.handler import is_owner

from library_core import (  # noqa: F401 — часть имён нужна другим модулям через images_library
    ALBUM_WAIT,
    CATS,
    REPORT_WAIT,
    LIBRARY_PHRASES,
    _collections,
    action_for,
    find_collection_action,
    guess_target,
    normalize_tag,
    phrases_for,
    pick,
    prime_collections,
    prime_links,
    reload_collections,
    reload_links,
    resolve_tag,
    stem,
    tag_from_caption,
    tags_for,
    trigger_matches,
)


logger = logging.getLogger("maruska.library")

router = Router(name="library")

# ---------------------------------------------------------
# Загрузка через личку
# ---------------------------------------------------------

# альбом: media_group_id -> {"photos": [...], "tag": ..., "message": первое сообщение}
_albums: dict[str, dict] = {}

# последний хэштег владельца: user_id -> (тег, время)
_last_tag: dict[int, tuple[str, float]] = {}

# накопленный отчёт по серии загрузок: user_id -> {...}
_reports: dict[int, dict] = {}


def is_upload(message: Message) -> bool:
    return (
        message.chat.type == "private"
        and message.from_user is not None
        and is_owner(message.from_user.id)
        and bool(message.photo)
    )


@router.message(is_upload)
async def upload_photo(message: Message):
    photo = message.photo[-1]
    item = (photo.file_id, photo.file_unique_id)
    tag = tag_from_caption(message.caption)

    # Одиночное фото — сразу
    if not message.media_group_id:
        await save_batch(message, tag, [item])
        return

    # Альбом приходит пачкой отдельных сообщений; подпись обычно
    # только у одного из них — собираем всё и сохраняем разом
    key = message.media_group_id
    album = _albums.get(key)

    if album is None:
        album = _albums[key] = {"photos": [], "tag": None, "message": message}
        asyncio.create_task(_flush_album(key))

    album["photos"].append(item)
    album["tag"] = album["tag"] or tag


async def _flush_album(key: str) -> None:
    await asyncio.sleep(ALBUM_WAIT)
    album = _albums.pop(key, None)

    if album:
        await save_batch(album["message"], album["tag"], album["photos"])


async def save_batch(message: Message, tag: str | None, photos: list) -> None:
    import time

    user_id = message.from_user.id
    now = time.monotonic()

    tag = resolve_tag(tag, _last_tag.get(user_id), now)

    if not tag:
        await message.reply(
            "Добавь подпись с хэштегом, например <code>#пиво</code> — "
            "так я пойму, в какую коллекцию положить фото."
        )
        return

    _last_tag[user_id] = (tag, now)

    from database.repository import add_library_images

    added, duplicates = await add_library_images(tag, photos, user_id)

    # Новый хэштег — сначала отчитываемся за предыдущую серию
    report = _reports.get(user_id)

    if report and report["tag"] != tag:
        report["task"].cancel()
        await _send_report(user_id)
        report = None

    if report is None:
        report = _reports[user_id] = {"tag": tag, "added": 0, "duplicates": 0, "message": message, "task": None}
    else:
        report["task"].cancel()

    report["added"] += added
    report["duplicates"] += duplicates
    report["task"] = asyncio.create_task(_report_later(user_id))


async def _report_later(user_id: int) -> None:
    try:
        await asyncio.sleep(REPORT_WAIT)
    except asyncio.CancelledError:
        return

    await _send_report(user_id)


async def _send_report(user_id: int) -> None:
    """Один отчёт на всю серию, а не по ответу на каждый альбом."""
    report = _reports.pop(user_id, None)

    if report is None:
        return

    tag, added, duplicates, message = report["tag"], report["added"], report["duplicates"], report["message"]

    from database.repository import all_library_links, library_summary, set_library_link

    from database.repository import ensure_library_collection

    # Новая коллекция — пробуем привязать сама
    linked_text = ""
    links = [target for t, target in await all_library_links() if t == tag]
    created = False

    if not links:
        target = guess_target(tag)

        if target:
            await set_library_link(tag, target, True)
            links = [target]

        # Не совпала ни с одним действием — становится своим действием
        created = await ensure_library_collection(tag, as_action=not target)

    await reload_links()
    await reload_collections()

    if links:
        names = []
        from actions.catalog import ACTIONS

        by_key = {a.key: a for a in ACTIONS}
        for target in links:
            if target == CATS:
                names.append("🐱 котики")
            elif target in by_key:
                names.append(f"{by_key[target].emoji} {by_key[target].item_acc or target}")
        linked_text = "\nПривязана к: " + ", ".join(names)
    elif (_collections.get(tag) or {}).get("as_action"):
        linked_text = (f"\n🆕 Это новое действие: ответь кому-нибудь в группе словом «{tag}» — "
                       "придёт фото из коллекции." if created else
                       f"\nРаботает как действие «{tag}».")
    else:
        linked_text = "\n⚠️ Коллекция ни к чему не привязана — настрой в панели: Маруська → Моя коллекция."

    audit.log("actions", "library_upload", actor_kind="admin", actor_id=message.from_user.id,
              actor_name=message.from_user.first_name, details=f"#{tag}: +{added}")

    total = next((row["count"] for row in await library_summary() if row["tag"] == tag), added)

    try:
        await message.reply(
            f"✅ Коллекция «{tag}»: добавлено {added} фото"
            + (f", {duplicates} уже были" if duplicates else "")
            + f". Всего в коллекции: {total}."
            + linked_text
            + "\n\nЕщё пачка без подписи в ближайшие 2 минуты — уйдёт сюда же."
        )
    except Exception as error:
        logger.warning("LIBRARY REPORT: %s", error)


@router.message(Command("collections"))
async def collections_command(message: Message):
    if message.chat.type != "private" or not message.from_user or not is_owner(message.from_user.id):
        return

    from database.repository import library_summary

    rows = await library_summary()

    if not rows:
        await message.reply(
            "Коллекций пока нет. Пришли фото или альбом с подписью <code>#пиво</code> — "
            "и появится первая."
        )
        return

    lines = ["📚 <b>Мои коллекции</b>\n"]

    for row in rows:
        lines.append(
            f"#{row['tag'].replace(' ', '_')} — {row['count']} фото, показано {row['shows']}"
            + ("" if row["targets"] else " · ⚠️ не привязана")
        )

    lines.append("\nДобавить: фото или альбом с подписью #название")
    await message.reply("\n".join(lines))
