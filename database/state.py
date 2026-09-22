"""
Активные раунды в памяти процесса.

Фильтр сообщений должен быть синхронным и быстрым: запрос в базу
на каждое сообщение чата недопустим. База остаётся источником
правды и используется для статистики и восстановления после
перезапуска.
"""

from dataclasses import dataclass


@dataclass
class Round:
    round_id: int
    chat_id: int
    host_id: int
    host_name: str
    word: str
    level: str
    status: str = "waiting"      # waiting | playing
    token: str = ""
    message_id: int | None = None
    hints_used: int = 0
    hint_message_id: int | None = None
    last_hint_at: float = 0.0


_rounds: dict[int, Round] = {}


def start(item: Round) -> None:
    _rounds[item.chat_id] = item


def get(chat_id: int) -> Round | None:
    return _rounds.get(chat_id)


def drop(chat_id: int) -> Round | None:
    return _rounds.pop(chat_id, None)


def active_chats() -> list[int]:
    return list(_rounds)
