"""
Проверка «Главных админов»: назначенные создателем люди получают права
как у OWNER_IDS, управлять списком может только создатель.

Запуск:  python test_owners.py
С настоящей базой (создаёт таблицы в указанной БД):
         TEST_DATABASE_URL=postgresql://… python test_owners.py
"""

import asyncio
import json
import os
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).parent
sys.path.insert(0, str(ROOT))

os.environ["OWNER_IDS"] = "111"
DB_URL = os.getenv("TEST_DATABASE_URL", "")
os.environ.setdefault("DATABASE_URL", DB_URL or "postgresql://unused@localhost/unused")

failures, checks = [], 0


def expect(label, got, want):
    global checks
    checks += 1
    if got != want:
        failures.append(f"  {label}: получили {got!r}, ждали {want!r}")


# --- права в памяти -------------------------------------------------------

from settings import handler  # noqa: E402

expect("создатель — владелец", handler.is_owner(111), True)
expect("создатель", handler.is_creator(111), True)
expect("чужой — не владелец", handler.is_owner(222), False)
handler.set_granted_owners([222])
expect("главный админ — владелец", handler.is_owner(222), True)
expect("главный админ — не создатель", handler.is_creator(222), False)
handler.set_granted_owners([])
expect("снятый — не владелец", handler.is_owner(222), False)
expect("пустой id", handler.is_owner(None), False)

# Панель: пункт только у создателя, скрипт подключён, маршруты на сервере.
settings_js = (ROOT / "webapp/static/admin/settings.js").read_text(encoding="utf-8")
expect("пункт меню для создателя", '["owners", "crown", "Главные админы", "Права как у создателя", "creator"' in settings_js, True)
expect("скрипт в панели", "/admin-assets/owners.js" in (ROOT / "webapp/static/admin.html").read_text(encoding="utf-8"), True)
expect("маршруты на сервере", "setup_owner_routes(app)" in (ROOT / "webapp/server.py").read_text(encoding="utf-8"), True)
expect("загрузка при старте", "owners.load()" in (ROOT / "bot.py").read_text(encoding="utf-8"), True)


# --- база и API -----------------------------------------------------------

async def with_database():
    from aiohttp.test_utils import make_mocked_request

    from database.database import engine, init_db, session_scope
    from database.models import BotOwner, User
    from settings import owners
    from sqlalchemy import delete

    await init_db()
    async with session_scope() as session:
        await session.execute(delete(BotOwner))
        await session.execute(delete(User).where(User.telegram_id.in_([111, 333, 444])))
        session.add(User(telegram_id=333, username="Masha_Admin", first_name="Маша"))
        session.add(User(telegram_id=111, username="creator", first_name="Стас"))
        await session.commit()

    audit_log = []
    sys.modules["audit"] = types.SimpleNamespace(log=lambda *a, **k: audit_log.append((a, k)))
    current = {"admin": {"id": 111, "first_name": "Стас"}}

    async def fake_admin(request):
        return current["admin"], []

    sys.modules["webapp.admin_v2"] = types.SimpleNamespace(_admin=fake_admin, _name=lambda a: a.get("first_name") or str(a["id"]))
    import webapp.owners_api as api
    from aiohttp import web

    def request(method, path, body=None, match=None):
        req = make_mocked_request(method, path, match_info=match or {})

        async def read_json():
            return body

        req.json = read_json
        return req

    async def call(handler_fn, *args, **kwargs):
        try:
            res = await handler_fn(request(*args, **kwargs))
            return res.status, json.loads(res.text)
        except web.HTTPException as error:
            return error.status, None

    # Назначение по @username (без учёта регистра) — права появляются сразу.
    status, body = await call(api.api_owner_add, "POST", "/api/admin/owners", {"user": "@masha_admin"})
    expect("назначение по @username", (status, body["admin"]["id"]), (200, 333))
    expect("права сразу", handler.is_owner(333), True)
    expect("журнал", audit_log[-1][0], ("roles", "Назначен главный админ"))

    # По ID незнакомого боту человека — тоже можно.
    status, _ = await call(api.api_owner_add, "POST", "/api/admin/owners", {"user": "444"})
    expect("назначение по ID", status, 200)

    status, body = await call(api.api_owner_add, "POST", "/api/admin/owners", {"user": "@masha_admin"})
    expect("повтор", (status, body["error"]), (409, "Уже главный админ"))
    status, body = await call(api.api_owner_add, "POST", "/api/admin/owners", {"user": "111"})
    expect("создателя не назначить", status, 409)
    status, body = await call(api.api_owner_add, "POST", "/api/admin/owners", {"user": "@nobody_here"})
    expect("неизвестный @username", status, 404)

    status, body = await call(api.api_owners, "GET", "/api/admin/owners")
    expect("список", [a["id"] for a in body["admins"]], [333, 444])
    expect("имя из базы", body["admins"][0]["name"], "Маша")
    expect("создатель в списке", [(c["id"], c["name"]) for c in body["creators"]], [(111, "Стас")])

    # Главный админ не управляет списком.
    current["admin"] = {"id": 333, "first_name": "Маша"}
    status, _ = await call(api.api_owners, "GET", "/api/admin/owners")
    expect("главный админ не видит список", status, 403)
    status, _ = await call(api.api_owner_remove, "POST", "/api/admin/owners/444/remove", match={"id": "444"})
    expect("главный админ не снимает", status, 403)
    current["admin"] = {"id": 111, "first_name": "Стас"}

    # Перезапуск: список поднимается из базы.
    handler.set_granted_owners([])
    await owners.load()
    expect("после перезапуска", sorted(handler.granted_owners()), [333, 444])

    status, _ = await call(api.api_owner_remove, "POST", "/api/admin/owners/444/remove", match={"id": "444"})
    expect("снятие", status, 200)
    expect("права сняты", handler.is_owner(444), False)
    expect("остальные на месте", handler.is_owner(333), True)
    status, _ = await call(api.api_owner_remove, "POST", "/api/admin/owners/444/remove", match={"id": "444"})
    expect("повторное снятие", status, 404)

    async with session_scope() as session:
        await session.execute(delete(BotOwner))
        await session.execute(delete(User).where(User.telegram_id.in_([111, 333, 444])))
        await session.commit()
    await engine.dispose()


if DB_URL:
    asyncio.run(with_database())
else:
    print("ℹ️  TEST_DATABASE_URL не задан — проверки с базой пропущены")

if failures:
    print(f"❌ {len(failures)} проблем:\n")
    print("\n".join(failures))
    sys.exit(1)
print(f"✅ Все {checks} проверок «Главных админов» прошли.")
