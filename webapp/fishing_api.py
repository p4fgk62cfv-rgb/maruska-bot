"""
API мини-приложения «Рыбалка» на сервере Мары.

Сервер главный: рыбу, вес, трофей, алмазы и опыт решает он.
Телефон игрока просит «заброс» и сообщает, вытащил ли рыбу в
мини-игре. Записать себе состояние, алмазы или улов клиент не может.

Игрок:
  GET  /api/fishing/profile      — снаряжение, улов, задания; алмазы и уровень — общие с Марой
  POST /api/fishing/cast         — заброс (сервер выбирает рыбу)
  POST /api/fishing/land         — {cast_id, success} — итог вываживания
  POST /api/fishing/select       — водоём, удочка, катушка, поплавок, лодка, наживка
  POST /api/fishing/buy          — {kind: rod|upgrade|reel|bobber|boat|bait, key}
  POST /api/fishing/chest        — открыть сундук рыбака
  GET  /api/fishing/leaderboard  — топ (группы, если игра открыта из группы)

Админка:
  GET  /api/admin/fishing        — статистика, рекорды, шансы, настройки
  POST /api/admin/fishing        — настройки (только владелец)

Группа: игру открывают по ссылке t.me/<бот>/fishing?startapp=g<id группы>.
Telegram подписывает start_param вместе с initData, а сервер ещё и
проверяет, что игрок состоит в этой группе, — только тогда крупный
улов объявляется в чате.
"""

import logging
import time

from aiohttp import web

import audit


logger = logging.getLogger("maruska.fishing.api")

# Не чаще одного запроса в 0.3 с от игрока — защита от автокликеров
_last_hit: dict[int, float] = {}


def _json_error(text: str, status: int = 400) -> web.Response:
    return web.json_response({"ok": False, "error": text}, status=status)


def parse_start_param(value: str | None) -> int | None:
    """«g1001234567890» → -1001234567890. Любой другой формат — None."""
    if not value or not value.startswith("g") or not value[1:].isdigit():
        return None
    return -int(value[1:])


def _player(request) -> tuple[int, str, int | None]:
    """(id, имя, группа из start_param) по подписанным данным Telegram."""
    from webapp.server import verify_init_data

    parsed = verify_init_data(request.headers.get("X-Telegram-Init-Data", ""), request.app["bot_token"])

    if parsed is None:
        raise web.HTTPUnauthorized(text="bad Telegram initData")

    user = parsed.get("user") or {}
    uid = user.get("id")

    if not uid:
        raise web.HTTPUnauthorized(text="no Telegram user")

    name = " ".join(filter(None, [user.get("first_name"), user.get("last_name")])) or user.get("username") or "Рыбак"

    return int(uid), name, parse_start_param(parsed.get("start_param"))


def _throttle(uid: int) -> None:
    now = time.monotonic()
    if now - _last_hit.get(uid, 0) < 0.3:
        raise web.HTTPTooManyRequests(text="slow down")
    _last_hit[uid] = now


async def _group_for(uid: int, chat_id: int | None) -> int | None:
    """Группа засчитывается, только если игрок в ней состоит и рыбалка там включена."""
    if chat_id is None:
        return None

    from settings.store import is_enabled
    from sqlalchemy import select

    from database.database import session_scope
    from database.models import GroupMember

    if not is_enabled(chat_id, "fishing"):
        return None

    async with session_scope() as session:
        member = (await session.execute(
            select(GroupMember.id).where(GroupMember.chat_id == chat_id, GroupMember.telegram_id == uid,
                                         GroupMember.left_at.is_(None))
        )).scalar_one_or_none()

    return chat_id if member else None


# ---------------------------------------------------------
# Игрок
# ---------------------------------------------------------

async def api_profile(request):
    from fishing import service as fs

    uid, _name, chat = _player(request)
    data = await fs.profile(uid)
    data["group"] = await _group_for(uid, chat)
    return web.json_response(data)


async def api_cast(request):
    from fishing import service as fs

    uid, _name, chat = _player(request)
    _throttle(uid)

    try:
        return web.json_response({"ok": True, **await fs.cast(uid, await _group_for(uid, chat))})
    except fs.FishingError as error:
        return _json_error(str(error))


async def api_land(request):
    from fishing import service as fs

    uid, name, _chat = _player(request)
    body = await request.json()

    try:
        result = await fs.land(uid, str(body.get("cast_id") or ""), bool(body.get("success")), display_name=name)
    except fs.FishingError as error:
        return _json_error(str(error))

    # Крупный улов — в группу, из которой открыли игру
    text = fs.announcement(result, name)

    if text:
        try:
            await request.app["bot"].send_message(result["chat_id"], text)
        except Exception as error:
            logger.warning("FISHING ANNOUNCE: %s", error)

    result["profile"] = await fs.profile(uid)
    return web.json_response({"ok": True, **result})


async def api_select(request):
    from fishing import service as fs

    uid, _name, _chat = _player(request)
    body = await request.json()

    try:
        data = await fs.choose_gear(uid, location=body.get("location"), rod=body.get("rod"),
                                    boat=body.get("boat"), bait=body.get("bait"),
                                    reel=body.get("reel"), bobber=body.get("bobber"))
    except fs.FishingError as error:
        return _json_error(str(error))

    return web.json_response({"ok": True, "profile": data})


async def api_buy(request):
    from fishing import service as fs

    uid, _name, _chat = _player(request)
    _throttle(uid)
    body = await request.json()

    try:
        data = await fs.buy(uid, str(body.get("kind") or ""), str(body.get("key") or ""))
    except fs.FishingError as error:
        return _json_error(str(error))

    return web.json_response({"ok": True, "profile": data})


async def api_chest(request):
    from fishing import service as fs

    uid, _name, _chat = _player(request)
    _throttle(uid)

    try:
        return web.json_response({"ok": True, **await fs.open_chest(uid)})
    except fs.FishingError as error:
        return _json_error(str(error))


async def api_leaderboard(request):
    from fishing import service as fs

    uid, _name, chat = _player(request)
    group = await _group_for(uid, chat)

    return web.json_response({"group": group, "top": await fs.leaderboard(group, 20)})


# ---------------------------------------------------------
# Админка
# ---------------------------------------------------------

async def api_admin_fishing(request):
    from fishing import service as fs
    from settings.handler import is_owner
    from webapp.admin_v2 import _admin, _name

    admin, _chats = await _admin(request)

    if request.method == "POST":
        if not is_owner(admin["id"]):
            raise web.HTTPForbidden(text="owner only")

        saved = await fs.save_settings(await request.json())
        audit.log("games", "fishing_settings", actor_kind="admin", actor_id=admin["id"],
                  actor_name=_name(admin), details=", ".join(f"{k}={v}" for k, v in saved.items()))

    data = await fs.admin_stats()
    data["owner"] = is_owner(admin["id"])
    return web.json_response(data)


def setup_fishing_routes(app):
    app.router.add_get("/api/fishing/profile", api_profile)
    app.router.add_post("/api/fishing/cast", api_cast)
    app.router.add_post("/api/fishing/land", api_land)
    app.router.add_post("/api/fishing/select", api_select)
    app.router.add_post("/api/fishing/buy", api_buy)
    app.router.add_post("/api/fishing/chest", api_chest)
    app.router.add_get("/api/fishing/leaderboard", api_leaderboard)

    app.router.add_get("/api/admin/fishing", api_admin_fishing)
    app.router.add_post("/api/admin/fishing", api_admin_fishing)
