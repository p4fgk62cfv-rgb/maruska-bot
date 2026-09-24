"""
Проверка правил магазина группы: цена, доступность, склад.
Запуск:  python test_shop_rules.py
"""

import pathlib
import re
import sys
from types import SimpleNamespace

ROOT = pathlib.Path(__file__).parent
sys.path.insert(0, str(ROOT))

from economy import shop_rules
from economy.shop import ITEM_BY_KEY, ITEMS


def main() -> int:
    failures, checks = [], 0

    def expect(label, got, want):
        nonlocal checks
        checks += 1
        if got != want:
            failures.append(f"  {label}: получили {got!r}, ждали {want!r}")

    a, b, c = ITEMS[0], ITEMS[1], ITEMS[2]

    shop_rules.prime(-100, [
        SimpleNamespace(item_key=a.key, price=7, enabled=True, stock=None),
        SimpleNamespace(item_key=b.key, price=None, enabled=False, stock=None),
        SimpleNamespace(item_key=c.key, price=None, enabled=True, stock=1),
    ])

    expect("своя цена", shop_rules.price(-100, a), 7)
    expect("цена каталога без правил", shop_rules.price(-100, b), b.price)
    expect("в другой группе — каталог", shop_rules.price(-200, a), a.price)
    expect("без группы — каталог", shop_rules.price(None, a), a.price)

    expect("снятый с продажи недоступен", shop_rules.available(-100, b), False)
    expect("в другой группе доступен", shop_rules.available(-200, b), True)
    expect("со склада 1 — доступен", shop_rules.available(-100, c), True)
    expect("ограничен", shop_rules.limited(-100, c), True)
    expect("не ограничен", shop_rules.limited(-100, a), False)

    shop_rules.note_sold(-100, c)
    expect("последний продан", shop_rules.stock_left(-100, c), 0)
    expect("распродан — недоступен", shop_rules.available(-100, c), False)

    shop_rules.note_returned(-100, c)
    expect("возврат на склад", shop_rules.available(-100, c), True)

    # Обработчик магазина не должен брать цену из каталога напрямую:
    # иначе своя цена группы молча игнорируется
    handler = (ROOT / "economy" / "shop_handler.py").read_text(encoding="utf-8")

    checks += 1

    for number, line in enumerate(handler.splitlines(), start=1):
        if re.search(r"\bitem\.price\b", line):
            failures.append(f"  [обход] shop_handler.py:{number} берёт item.price в обход правил группы")

    checks += 1
    if "await reserve(" not in handler.split("async def gift_command")[1]:
        failures.append("  [обход] подарки не проверяют наличие и склад")

    if failures:
        print(f"❌ {len(failures)} проблем:\n")
        print("\n".join(failures))
        return 1

    print(f"✅ Все {checks} проверок магазина прошли.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
