"""
«🃏 Арена» в панели управления: всё, что владелец может сделать с игрой в дурака.

Арена — отдельный сервис (arena/), у неё свой внутренний API под общим секретом.
Этот модуль — мост: проверяет, что панель открыл владелец бота (OWNER_IDS),
пропускает только разрешённые адреса и пишет каждое изменение в журнал аудита.

Переменные окружения бота:
  ARENA_URL              — адрес арены (https://…), тот же, что для кнопки /game
  ARENA_INTERNAL_SECRET  — тот же ключ, что INTERNAL_API_SECRET у арены
"""

import logging
import os
import re
import uuid

import aiohttp
from aiohttp import web

import audit

logger = logging.getLogger(__name__)

TIMEOUT = aiohttp.ClientTimeout(total=15)

# Что панель может прочитать и что — изменить. Всё остальное отклоняется, даже для владельца.
READ = [
    r"overview",
    r"players",
    r"players/\d{3,20}",
    r"live",
    r"tournaments",
    r"seasons",
    r"items",
    r"settings",
    r"moderation/reports",
    r"integrity/suspicious",
]
WRITE = {
    r"players/\d{3,20}/wallet": "Изменение баланса",
    r"players/\d{3,20}/premium": "Премиум",
    r"players/\d{3,20}/reset": "Сброс имени или аватарки",
    r"players/\d{3,20}/items": "Предмет игроку",
    r"games/[0-9a-f-]{36}/abort": "Отмена партии",
    r"rooms/[A-Z0-9]{8}/close": "Закрытие стола",
    r"tournaments/[0-9a-f-]{36}/cancel": "Отмена турнира",
    r"tournaments": "Новый турнир",
    r"seasons": "Новый сезон",
    r"seasons/[0-9a-f-]{36}/end": "Завершение сезона",
    r"items/[a-z0-9_]{2,64}": "Товар в магазине",
    r"broadcast": "Рассылка игрокам",
    r"moderation/ban": "Бан",
    r"moderation/unban": "Разбан",
    r"moderation/clawback": "Изъятие выигрыша",
}
# Эти адреса у арены лежат вне /internal/admin.
OUTSIDE_ADMIN = ("moderation/", "integrity/")


def arena_url() -> str:
    return os.getenv("ARENA_URL", "").strip().rstrip("/")


def arena_secret() -> str:
    return os.getenv("ARENA_INTERNAL_SECRET", "").strip()


def _target(method: str, path: str) -> str:
    # Бан, изъятие, подозрительные пары и создание турнира живут в /internal, остальное — в /internal/admin.
    if path.startswith(OUTSIDE_ADMIN) or (method == "POST" and path == "tournaments"):
        return f"{arena_url()}/api/internal/{path}"
    return f"{arena_url()}/api/internal/admin/{path}"


def _matches(patterns, path: str) -> str | None:
    for pattern in patterns:
        if re.fullmatch(pattern, path):
            return pattern
    return None


async def _owner(request):
    from settings.handler import is_owner
    from webapp.admin_v2 import _admin, _name

    admin, _chats = await _admin(request)
    if not is_owner(admin["id"]):
        raise web.HTTPForbidden(text="owner only")
    return admin, _name(admin)


async def _call(method: str, url: str, *, query=None, body=None):
    headers = {"Authorization": f"Bearer {arena_secret()}"}
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            async with session.request(method, url, params=query, json=body, headers=headers) as response:
                text = await response.text()
                return response.status, text
    except (aiohttp.ClientError, TimeoutError) as error:
        logger.warning("ARENA: %s %s failed: %s", method, url, error)
        return 502, '{"error":"ARENA_UNREACHABLE","message":"Арена не отвечает"}'


def _details(path: str, body: dict | None) -> str:
    if not body:
        return path
    shown = {k: v for k, v in body.items() if k not in ("requestId",)}
    text = ", ".join(f"{k}={v}" for k, v in shown.items())
    return f"{path}: {text}"[:500]


async def api_arena(request: web.Request):
    """GET/POST /api/admin/arena/{path} → внутренний API арены."""
    admin, admin_name = await _owner(request)

    if not arena_url() or not arena_secret():
        return web.json_response(
            {"ok": False, "error": "Арена не подключена: задайте ARENA_URL и ARENA_INTERNAL_SECRET у бота"},
            status=503,
        )

    path = request.match_info["path"].strip("/")
    body = None

    if request.method == "GET":
        if not _matches(READ, path):
            raise web.HTTPNotFound(text="unknown arena path")
    else:
        pattern = _matches(WRITE, path)
        if not pattern:
            raise web.HTTPNotFound(text="unknown arena path")
        try:
            body = await request.json() if request.can_read_body else {}
        except ValueError:
            raise web.HTTPBadRequest(text="bad json")
        if not isinstance(body, dict):
            raise web.HTTPBadRequest(text="bad json")
        # Кто сделал — для журнала арены; ключ запроса — чтобы повтор не списал дважды.
        if path.endswith("/wallet"):
            body.setdefault("requestId", uuid.uuid4().hex)
            body["admin"] = admin_name[:64]
        if path == "moderation/clawback":
            body.setdefault("requestId", uuid.uuid4().hex)

    status, text = await _call(request.method, _target(request.method, path), query=dict(request.query) or None, body=body)

    if request.method == "POST" and status < 400:
        title = WRITE[_matches(WRITE, path)]
        target = re.search(r"players/(\d+)", path)
        audit.log(
            "arena",
            title,
            actor_kind="admin",
            actor_id=admin["id"],
            actor_name=admin_name,
            target_id=int(target.group(1)) if target else None,
            details=_details(path, body),
        )

    if status >= 400:
        message = _arena_error(status, text)
        return web.json_response({"ok": False, "error": message}, status=status if status < 500 else 502)

    # Загруженные в Арене аватарки лежат на её домене: делаем адреса полными.
    text = text.replace('"photoUrl":"/api/avatars/', f'"photoUrl":"{arena_url()}/api/avatars/')
    return web.Response(text=text, content_type="application/json")


ERRORS = {
    "NOT_FOUND": "Не найдено",
    "INSUFFICIENT_FUNDS": "Недостаточно средств на счёте игрока",
    "VALIDATION_FAILED": "Проверьте введённые данные",
    "UNAUTHORIZED": "Ключ арены не подходит: сверьте ARENA_INTERNAL_SECRET и INTERNAL_API_SECRET",
    "ARENA_UNREACHABLE": "Арена не отвечает",
}


def _arena_error(status: int, text: str) -> str:
    match = re.search(r'"error"\s*:\s*"([A-Z_]+)"', text or "")
    if match and match.group(1) in ERRORS:
        return ERRORS[match.group(1)]
    return f"Арена ответила ошибкой ({status})"


def setup_arena_admin_routes(app: web.Application) -> None:
    app.router.add_get("/api/admin/arena/{path:.+}", api_arena)
    app.router.add_post("/api/admin/arena/{path:.+}", api_arena)
