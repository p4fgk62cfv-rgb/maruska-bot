"""
«Доступ групп» в панели — только для владельца бота.

  GET  /api/admin/access             — модули и все группы с их доступом
  POST /api/admin/access/{chat_id}   — {"all": true|false} или {"module": "arena", "on": true|false}

Новая группа получает функции Мары только после того, как владелец их здесь включит
(settings/access.py).
"""

from aiohttp import web

import audit


async def api_access(request: web.Request):
    from database.repository import list_known_chats
    from settings import access
    from webapp.owners_api import _owner

    await _owner(request)
    groups = []
    for chat in await list_known_chats():
        chat_id = int(chat["chat_id"])
        groups.append({
            "chat_id": chat_id,
            "title": chat.get("title") or str(chat_id),
            "members": chat.get("members", 0),
            "active": bool(chat.get("active")),
            "access": access.entry(chat_id),
        })
    # Сначала группы без доступа — они и ждут решения
    groups.sort(key=lambda g: (g["access"]["all"], len(g["access"]["modules"]), g["title"].lower()))
    return web.json_response({
        "modules": [{"key": key, "title": title, "hint": hint} for key, (title, hint) in access.MODULES.items()],
        "groups": groups,
    })


async def api_access_set(request: web.Request):
    from settings import access
    from webapp.owners_api import _owner

    admin, admin_name = await _owner(request)
    try:
        chat_id = int(request.match_info["chat_id"])
        body = await request.json()
    except (ValueError, TypeError):
        raise web.HTTPBadRequest(text="bad request")
    if chat_id >= 0:
        raise web.HTTPBadRequest(text="not a group")
    if "all" in body:
        result = await access.set_access(chat_id, everything=bool(body["all"]))
        what = "всё разрешено" if body["all"] else "всё выключено"
    elif body.get("module") in access.MODULES:
        result = await access.set_access(chat_id, module=body["module"], on=bool(body.get("on")))
        what = f"{access.MODULES[body['module']][0]}: {'вкл' if body.get('on') else 'выкл'}"
    else:
        raise web.HTTPBadRequest(text="unknown module")
    audit.log("access", "set", chat_id=chat_id, actor_kind="admin", actor_id=admin["id"], actor_name=admin_name,
              details=what)
    return web.json_response({"ok": True, "access": result})


def setup_access_routes(app: web.Application) -> None:
    app.router.add_get("/api/admin/access", api_access)
    app.router.add_post("/api/admin/access/{chat_id}", api_access_set)
