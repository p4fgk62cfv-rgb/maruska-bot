"""
Цветные логи.

Railway понимает ANSI-коды, поэтому строки можно раскрасить
по уровню: запуск и обычные события — зелёным, предупреждения —
жёлтым, ошибки — красным.

Отключается переменной LOG_COLOR=0 (например, если логи куда-то
пересылаются и коды мешают).
"""

import logging
import os
import sys


RESET = "\033[0m"

COLORS = {
    logging.DEBUG: "\033[90m",      # серый
    logging.INFO: "\033[32m",       # зелёный
    logging.WARNING: "\033[33m",    # жёлтый
    logging.ERROR: "\033[31m",      # красный
    logging.CRITICAL: "\033[97;41m",  # белым по красному
}

MARKS = {
    logging.DEBUG: "·",
    logging.INFO: "✅",
    logging.WARNING: "⚠️",
    logging.ERROR: "❌",
    logging.CRITICAL: "🔥",
}


def color_enabled() -> bool:
    value = os.getenv("LOG_COLOR", "1").strip().lower()
    return value not in ("0", "false", "no", "off")


class ColorFormatter(logging.Formatter):
    def __init__(self, fmt: str, use_color: bool = True):
        super().__init__(fmt)
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        mark = MARKS.get(record.levelno, "")
        original = record.msg

        # Значок ставим перед сообщением, не ломая аргументы
        record.msg = f"{mark} {original}" if mark else original

        try:
            text = super().format(record)
        finally:
            record.msg = original

        if not self.use_color:
            return text

        color = COLORS.get(record.levelno, "")

        return f"{color}{text}{RESET}" if color else text


class RingHandler(logging.Handler):
    """
    Держит последние записи в памяти — чтобы веб-панель могла
    показать, что происходило, без доступа к серверу.
    """

    def __init__(self, capacity: int = 300):
        super().__init__()
        self.capacity = capacity
        self.records: list[dict] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.records.append({
                "time": record.created,
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage()[:500],
            })

            if len(self.records) > self.capacity:
                del self.records[: len(self.records) - self.capacity]
        except Exception:
            pass

    def tail(self, limit: int = 100, level: str = "") -> list[dict]:
        items = self.records

        if level:
            items = [item for item in items if item["level"] == level]

        return list(reversed(items[-limit:]))


ring = RingHandler()


class RestartConflictFilter(logging.Filter):
    """
    «Conflict: terminated by other getUpdates request» при выкатке — не ошибка.

    Railway запускает новую копию бота, пока старая ещё работает, и пару
    секунд обе спрашивают Telegram об обновлениях. Telegram ругается,
    aiogram сам повторяет запрос, старая копия выключается — всё.
    Первые GRACE секунд после старта такие строки пишем спокойным INFO.
    Если конфликт держится дольше — значит, бот правда запущен дважды
    (например, локально с тем же токеном), и это остаётся ошибкой.
    """

    GRACE = 120.0

    def __init__(self):
        super().__init__()
        import time as _time

        self.started = _time.monotonic()
        self._time = _time
        self.told = False

    def filter(self, record: logging.LogRecord) -> bool:
        if self._time.monotonic() - self.started > self.GRACE:
            return True

        text = record.getMessage()

        if "TelegramConflictError" in text:
            if self.told:
                return False
            self.told = True
            record.levelno, record.levelname = logging.INFO, "INFO"
            record.msg, record.args = "Перезапуск: старая копия бота ещё выключается — жду пару секунд (это нормально)", None
            return True

        # «Sleep for 1 second and try again» после такого конфликта — тоже шум
        if self.told and "Sleep for" in text and "try again" in text:
            return False

        return True


def setup(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)

    handler.setFormatter(
        ColorFormatter(
            "%(asctime)s | %(levelname)-7s | %(message)s",
            use_color=color_enabled(),
        )
    )

    root = logging.getLogger()

    # Убираем возможные прежние обработчики, иначе строки задвоятся
    for existing in root.handlers[:]:
        root.removeHandler(existing)

    root.addHandler(handler)
    root.addHandler(ring)
    root.setLevel(level)

    # aiogram шумит на каждое сообщение — оставляем только важное
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)

    # Конфликт двух копий при выкатке на Railway — не ошибка, см. фильтр
    logging.getLogger("aiogram.dispatcher").addFilter(RestartConflictFilter())
