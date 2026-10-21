"""
Ночной бэкап базы: pg_dump всей базы (и Мары, и Арены) — файлом владельцу в личку.

Каждую ночь в BACKUP_HOUR по Москве Мара делает выгрузку в сжатом формате
pg_dump (-Fc) и присылает её тому, кто указан в BACKUP_TO (@ник или id;
по умолчанию @uastas). Telegram принимает от бота файлы до 50 МБ — большие
выгрузки уходят частями. Не получилось — приходит сообщение с причиной.

Восстановить:  pg_restore --clean --if-exists --no-owner -d "<адрес базы>" maruska-….dump
(части сначала склеить:  cat maruska-….dump.part* > maruska-….dump)

В админке (Система) — когда был последний бэкап и кнопка «Сделать бэкап сейчас».
"""

import asyncio
import logging
import os
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from aiogram.types import BufferedInputFile

logger = logging.getLogger("maruska.backup")

MSK = ZoneInfo("Europe/Moscow")
BACKUP_HOUR = int(os.getenv("BACKUP_HOUR", "4"))
CHECK_INTERVAL = 600                 # раз в 10 минут: не пора ли
DUMP_TIMEOUT = 15 * 60
PART_SIZE = 45 * 1024 * 1024         # Telegram: до 50 МБ на файл от бота
STATE_KEY = "backup_state"

_lock = asyncio.Lock()


def recipient_setting() -> str:
    return (os.getenv("BACKUP_TO", "") or "uastas").strip().lstrip("@")


def database_url() -> str:
    """Адрес базы для pg_dump: без «+asyncpg» в схеме."""
    url = os.getenv("DATABASE_URL", "").strip()
    return re.sub(r"^postgres(?:ql)?(?:\+\w+)?://", "postgresql://", url)


def hide_secrets(text: str) -> str:
    """Пароль из адреса базы в сообщения не попадает."""
    return re.sub(r"(postgres(?:ql)?(?:\+\w+)?://[^:/@\s]+:)[^@\s]+@", r"\1***@", text or "")


def human_size(size: int) -> str:
    if size < 1024 * 1024:
        return f"{max(size // 1024, 1)} КБ"
    return f"{size / 1024 / 1024:.1f} МБ".replace(".", ",")


def parts_of(data: bytes, size: int | None = None) -> list[bytes]:
    size = size or PART_SIZE
    return [data[i:i + size] for i in range(0, len(data), size)] or [b""]


def due(now: datetime, state: dict) -> bool:
    """Пора ли ночной бэкап: наступил час и сегодня ещё не пробовали."""
    return now.hour >= BACKUP_HOUR and state.get("day") != now.date().isoformat()


async def load_state() -> dict:
    from database.repository import get_group_settings

    return dict((await get_group_settings(0)).get(STATE_KEY) or {})


async def save_state(**fields) -> dict:
    from database.repository import set_group_setting

    state = {**await load_state(), **fields}
    await set_group_setting(chat_id=0, key=STATE_KEY, value=state)
    return state


async def dump() -> bytes:
    """Выгрузка всей базы. Ошибка — RuntimeError с понятной причиной."""
    pg_dump = shutil.which("pg_dump")
    if not pg_dump:
        raise RuntimeError("в контейнере нет pg_dump")
    url = database_url()
    if not url:
        raise RuntimeError("не задан DATABASE_URL")

    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "maruska.dump"
        process = await asyncio.create_subprocess_exec(
            pg_dump, "--format=custom", "--no-owner", "--no-privileges", "--file", str(path), "--dbname", url,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, err = await asyncio.wait_for(process.communicate(), DUMP_TIMEOUT)
        except asyncio.TimeoutError:
            process.kill()
            raise RuntimeError("pg_dump не уложился в 15 минут")
        if process.returncode != 0:
            lines = [line.strip() for line in err.decode(errors="replace").splitlines() if line.strip()] if err else []
            reason = hide_secrets(lines[0].removeprefix("pg_dump: ") if lines else "")
            raise RuntimeError(f"pg_dump: {reason or 'код ' + str(process.returncode)}")
        return path.read_bytes()


async def recipient_id() -> int | None:
    """Кому слать: @ник из BACKUP_TO (или id), иначе первый владелец бота."""
    target = recipient_setting()
    if target.lstrip("-").isdigit():
        return int(target)
    try:
        from database.repository import get_user_by_username

        user = await get_user_by_username(target)
        if user is not None:
            return user.telegram_id
    except Exception as error:
        logger.warning("BACKUP TO: %s %s", type(error).__name__, error)
    from settings.handler import OWNER_IDS

    return next(iter(sorted(OWNER_IDS)), None)


async def run_backup(bot, reason: str = "ночной") -> dict:
    """Делает бэкап и присылает его. Возвращает состояние для админки."""
    async with _lock:
        now = datetime.now(MSK)
        to = await recipient_id()
        if to is None:
            return await save_state(day=now.date().isoformat(), error=f"не знаю, кому слать: @{recipient_setting()}",
                                    tried_at=now.isoformat())
        try:
            data = await dump()
            stamp = now.strftime("%Y-%m-%d_%H-%M")
            name = f"maruska-{stamp}.dump"
            chunks = parts_of(data)
            for number, chunk in enumerate(chunks, start=1):
                file_name = name if len(chunks) == 1 else f"{name}.part{number}"
                caption = (f"🗄 Бэкап базы Маруськи ({reason}) — {now:%d.%m.%Y %H:%M} МСК, {human_size(len(data))}"
                           + (f"\nЧасть {number} из {len(chunks)}" if len(chunks) > 1 else "")
                           + "\nВосстановить: pg_restore --clean --if-exists --no-owner -d <адрес базы> файл")
                # Простым текстом: в подписи есть «<адрес базы>», HTML принял бы его за тег
                await bot.send_document(to, BufferedInputFile(chunk, filename=file_name), caption=caption,
                                        parse_mode=None)
            logger.info("BACKUP: %s, %s частей, отправлен %s", human_size(len(data)), len(chunks), to)
            return await save_state(day=now.date().isoformat(), ok_at=now.isoformat(), size=len(data),
                                    parts=len(chunks), error=None, tried_at=now.isoformat())
        except Exception as error:
            text = hide_secrets(str(error))[:300]
            logger.error("BACKUP: %s %s", type(error).__name__, text)
            try:
                await bot.send_message(to, f"⚠️ Бэкап базы не получился ({reason}): {text}", parse_mode=None)
            except Exception:
                pass
            return await save_state(day=now.date().isoformat(), error=text, tried_at=now.isoformat())


async def backup_loop(bot):
    """Раз в 10 минут: если наступил ночной час и сегодня бэкапа ещё не было — делаем."""
    while True:
        try:
            await asyncio.sleep(CHECK_INTERVAL)
            if due(datetime.now(MSK), await load_state()):
                await run_backup(bot)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.error("BACKUP LOOP: %s %s", type(error).__name__, error)
