"""
«Главные админы» в панели: создатель бота (OWNER_IDS) назначает людей
с такими же полными правами, как у него самого, и снимает их.

  GET  /api/admin/owners               — создатели и главные админы
  POST /api/admin/owners               — назначить: {"user": "123456789" | "@username"}
  POST /api/admin/owners/{id}/remove   — снять

Назначать и снимать может только создатель: главный админ не может
убрать другого главного админа или добавить кого-то сам.
"""

from aiohttp import web

import audit


async def _creator(request):
    from settings.handler import is_creator
    from webapp.admin_v2 import _admin, _name

    admin, _chats = await _admin(request)
    if not is_creator(admin["id"]):
        raise web.HTTPForbidden(text="creator only")
    return admin, _name(admin)


async def _creators() -> list[dict]:
    from sqlalchemy import select

    from database.database import session_scope
    from database.models import User
    from settings.handler import OWNER_IDS

    ids = sorted(OWNER_IDS)
    async with session_scope() as session:
        rows = (await session.execute(select(User.telegram_id, User.first_name, User.username).where(User.telegram_id.in_(ids)))).all()
    known = {r[0]: r for r in rows}
    return [
        {
            "id": i,
            "name": (known[i][1] if i in known else None) or (f"@{known[i][2]}" if i in known and known[i][2] else str(i)),
            "username": known[i][2] if i in known else None,
        }
        for i in ids
    ]


async def api_owners(request: web.Request):
    from settings import owners

    await _creator(request)
    return web.json_response({"creators": await _creators(), "admins": await owners.list_all()})


async def api_owner_add(request: web.Request):
    from settings import owners
    from settings.handler import OWNER_IDS, granted_owners

    admin, admin_name = await _creator(request)
    try:
        body = await request.json()
    except ValueError:
        raise web.HTTPBadRequest(text="bad json")
    query = str((body or {}).get("user") or "").strip()
    if not query:
        return web.json_response({"ok": False, "error": "Укажите Telegram ID или @username"}, status=400)

    person = await owners.find_user(query)
    if person is None:
        return web.json_response(
            {"ok": False, "error": "Не нашла такого пользователя. Пусть напишет боту в личку, или укажите его Telegram ID"},
            status=404,
        )
    if person["id"] in OWNER_IDS:
        return web.json_response({"ok": False, "error": "Это создатель — у него уже все права"}, status=409)
    if person["id"] in granted_owners():
        return web.json_response({"ok": False, "error": "Уже главный админ"}, status=409)

    name = person["name"] or (f"@{person['username']}" if person["username"] else None)
    await owners.grant(person["id"], name, admin["id"])
    audit.log(
        "roles", "Назначен главный админ",
        actor_kind="admin", actor_id=admin["id"], actor_name=admin_name,
        target_id=person["id"], details=name or str(person["id"]),
    )
    return web.json_response({"ok": True, "admin": {"id": person["id"], "name": name or str(person["id"])}})


async def api_owner_remove(request: web.Request):
    from settings import owners
    from settings.handler import granted_owners

    admin, admin_name = await _creator(request)
    try:
        target = int(request.match_info["id"])
    except ValueError:
        raise web.HTTPBadRequest(text="bad id")
    if target not in granted_owners():
        raise web.HTTPNotFound(text="not an admin")

    await owners.revoke(target)
    audit.log(
        "roles", "Снят главный админ",
        actor_kind="admin", actor_id=admin["id"], actor_name=admin_name,
        target_id=target, details=str(target),
    )
    return web.json_response({"ok": True})


def setup_owner_routes(app: web.Application) -> None:
    app.router.add_get("/api/admin/owners", api_owners)
    app.router.add_post("/api/admin/owners", api_owner_add)
    app.router.add_post("/api/admin/owners/{id}/remove", api_owner_remove)
