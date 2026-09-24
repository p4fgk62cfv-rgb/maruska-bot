"""
Правила магазина для группы: своя цена, доступность, остаток.

Каталог товаров общий (economy/shop.py), а цены и наличие у каждой
группы свои. Покупка в группе идёт по её правилам. Кэш в памяти,
загружается вместе с настройками группы.
"""

from dataclasses import dataclass


@dataclass
class Rule:
    price: int | None = None
    enabled: bool = True
    stock: int | None = None


_cache: dict[int, dict[str, Rule]] = {}

MAX_PRICE = 1_000_000


def prime(chat_id: int, rows) -> None:
    _cache[chat_id] = {
        row.item_key: Rule(price=row.price, enabled=row.enabled, stock=row.stock)
        for row in rows
    }


def is_loaded(chat_id: int) -> bool:
    return chat_id in _cache


async def reload(chat_id: int) -> None:
    from database.repository import list_shop_overrides

    prime(chat_id, await list_shop_overrides(chat_id))


def rule(chat_id: int | None, item_key: str) -> Rule:
    if chat_id is None:
        return Rule()
    return _cache.get(chat_id, {}).get(item_key) or Rule()


def price(chat_id: int | None, item) -> int:
    own = rule(chat_id, item.key).price
    return item.price if own is None else own


def available(chat_id: int | None, item) -> bool:
    """Включён и есть на складе (или склад не ограничен)."""
    r = rule(chat_id, item.key)
    return r.enabled and (r.stock is None or r.stock > 0)


def limited(chat_id: int | None, item) -> bool:
    return rule(chat_id, item.key).stock is not None


def stock_left(chat_id: int | None, item) -> int | None:
    return rule(chat_id, item.key).stock


def note_sold(chat_id: int, item) -> None:
    """После покупки уменьшаем остаток и в кэше."""
    r = _cache.get(chat_id, {}).get(item.key)

    if r is not None and r.stock is not None and r.stock > 0:
        r.stock -= 1


def note_returned(chat_id: int, item) -> None:
    r = _cache.get(chat_id, {}).get(item.key)

    if r is not None and r.stock is not None:
        r.stock += 1
