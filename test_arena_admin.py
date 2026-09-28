"""
Проверка раздела «🃏 Арена» в панели: мост к арене пускает только владельца,
пропускает только разрешённые адреса, пишет журнал и не теряет ключ запроса.
Запуск:  python test_arena_admin.py
"""

import asyncio
import json
import os
import pathlib
import re
import sys
import types

ROOT = pathlib.Path(__file__).parent
sys.path.insert(0, str(ROOT))


# --- заглушки: в тестах нет aiohttp и базы -------------------------------

class HTTPError(Exception):
    def __init__(self, text=""):
        super().__init__(text)
        self.text = text


class HTTPForbidden(HTTPError):
    status = 403


class HTTPNotFound(HTTPError):
    status = 404


class HTTPBadRequest(HTTPError):
    status = 400


class Response:
    def __init__(self, text="", content_type=None, status=200):
        self.text, self.status = text, status


def json_response(data, status=200):
    return Response(json.dumps(data, ensure_ascii=False), status=status)


web = types.SimpleNamespace(
    HTTPForbidden=HTTPForbidden, HTTPNotFound=HTTPNotFound, HTTPBadRequest=HTTPBadRequest,
    Response=Response, json_response=json_response, Request=object, Application=object,
)
aiohttp = types.ModuleType("aiohttp")
aiohttp.web = web
aiohttp.ClientTimeout = lambda **kw: None
aiohttp.ClientError = OSError
sys.modules["aiohttp"] = aiohttp
sys.modules["aiohttp.web"] = web

AUDIT = []
audit = types.ModuleType("audit")
audit.log = lambda category, action, **fields: AUDIT.append((category, action, fields))
sys.modules["audit"] = audit

OWNERS = {111}
handler = types.ModuleType("settings.handler")
handler.is_owner = lambda uid: uid in OWNERS
sys.modules.setdefault("settings", types.ModuleType("settings"))
sys.modules["settings.handler"] = handler

CURRENT = {"admin": {"id": 111, "first_name": "Стас"}}


async def fake_admin(request):
    return CURRENT["admin"], []


admin_v2 = types.ModuleType("webapp.admin_v2")
admin_v2._admin = fake_admin
admin_v2._name = lambda a: a.get("first_name") or str(a["id"])
sys.modules["webapp.admin_v2"] = admin_v2

import webapp.arena_admin as bridge  # noqa: E402

CALLS = []


async def fake_call(method, url, *, query=None, body=None):
    CALLS.append((method, url, query, body))
    if url.endswith("/missing"):
        return 404, '{"error":"NOT_FOUND"}'
    if url.endswith("/wallet") and body and body.get("amount", 0) < -1000:
        return 409, '{"error":"INSUFFICIENT_FUNDS"}'
    return 200, '{"ok":true,"photoUrl":"/api/avatars/abc?v=1"}'


bridge._call = fake_call


class FakeRequest:
    def __init__(self, method, path, body=None, query=None):
        self.method, self.match_info, self.query = method, {"path": path}, query or {}
        self._body = body
        self.can_read_body = body is not None

    async def json(self):
        return self._body


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if sys.version_info < (3, 10) else asyncio.run(coro)


def main() -> int:
    failures, checks = [], 0

    def expect(label, got, want):
        nonlocal checks
        checks += 1
        if got != want:
            failures.append(f"  {label}: получили {got!r}, ждали {want!r}")

    os.environ["ARENA_URL"] = "https://arena.test/"
    os.environ["ARENA_INTERNAL_SECRET"] = "s3cret"

    # --- куда уходит запрос ---
    expect("карточка игрока", bridge._target("GET", "players/123456"), "https://arena.test/api/internal/admin/players/123456")
    expect("бан — вне /admin", bridge._target("POST", "moderation/ban"), "https://arena.test/api/internal/moderation/ban")
    expect("новый турнир — вне /admin", bridge._target("POST", "tournaments"), "https://arena.test/api/internal/tournaments")
    expect("список турниров — в /admin", bridge._target("GET", "tournaments"), "https://arena.test/api/internal/admin/tournaments")

    # --- белый список: всё, что зовёт панель, разрешено; лишнее — нет ---
    reads = ["overview", "players", "players/123456789", "live", "tournaments", "seasons", "items", "settings", "moderation/reports", "integrity/suspicious"]
    writes = [
        "players/123456789/wallet", "players/123456789/premium", "players/123456789/reset", "players/123456789/items",
        "games/0192a5b0-1234-7abc-8def-0123456789ab/abort", "rooms/ABCD1234/close", "tournaments",
        "tournaments/0192a5b0-1234-7abc-8def-0123456789ab/cancel", "seasons", "seasons/0192a5b0-1234-7abc-8def-0123456789ab/end",
        "items/back_wolf", "broadcast", "moderation/ban", "moderation/unban", "moderation/clawback",
    ]
    for path in reads:
        expect(f"чтение {path}", bool(bridge._matches(bridge.READ, path)), True)
    for path in writes:
        expect(f"запись {path}", bool(bridge._matches(bridge.WRITE, path)), True)
    for path in ["players/../../x", "metrics", "players/abc/wallet", "items/BAD KEY", "stats"]:
        expect(f"закрыто {path}", bool(bridge._matches(bridge.READ, path) or bridge._matches(bridge.WRITE, path)), False)

    # Каждый адрес из arena.js закрыт белым списком (сравниваем начала строк).
    js = (ROOT / "webapp" / "static" / "admin" / "arena.js").read_text(encoding="utf-8")
    used = set(re.findall(r'\bAP?\("([a-z_/]+)', js))
    for prefix in sorted(used):
        checks += 1
        sample = [p for p in reads + writes if p.startswith(prefix)]
        if not sample:
            failures.append(f"  [arena.js] зовёт {prefix}…, а мост это не пропускает")

    # --- права ---
    CURRENT["admin"] = {"id": 222, "first_name": "Модератор"}
    try:
        run(bridge.api_arena(FakeRequest("GET", "overview")))
        failures.append("  не-владелец открыл Арену")
    except HTTPForbidden:
        pass
    checks += 1
    CURRENT["admin"] = {"id": 111, "first_name": "Стас"}

    # Без настроек — понятная ошибка, а не падение.
    os.environ.pop("ARENA_INTERNAL_SECRET")
    res = run(bridge.api_arena(FakeRequest("GET", "overview")))
    expect("не настроено → 503", res.status, 503)
    os.environ["ARENA_INTERNAL_SECRET"] = "s3cret"

    # Чтение: аватарки получают адрес арены.
    res = run(bridge.api_arena(FakeRequest("GET", "players/123456789")))
    expect("полный адрес аватарки", json.loads(res.text)["photoUrl"], "https://arena.test/api/avatars/abc?v=1")
    expect("чтение не пишет журнал", len(AUDIT), 0)

    # Неизвестный адрес — 404 до обращения к арене.
    before = len(CALLS)
    try:
        run(bridge.api_arena(FakeRequest("POST", "metrics", {})))
        failures.append("  мост пропустил неразрешённую запись")
    except HTTPNotFound:
        pass
    checks += 1
    expect("арена не вызвана", len(CALLS), before)

    # Деньги: ключ запроса и имя админа добавляются, журнал пишется с Telegram ID игрока.
    run(bridge.api_arena(FakeRequest("POST", "players/123456789/wallet", {"currency": "CREDITS", "amount": 5000, "reason": "компенсация"})))
    method, url, _q, body = CALLS[-1]
    expect("метод", method, "POST")
    expect("ключ запроса", bool(body.get("requestId")), True)
    expect("админ", body.get("admin"), "Стас")
    expect("журнал", AUDIT[-1][:2], ("arena", "Изменение баланса"))
    expect("цель в журнале", AUDIT[-1][2].get("target_id"), 123456789)
    expect("ключ не в журнале", "requestId" in AUDIT[-1][2].get("details", ""), False)

    # Ошибка арены переводится на русский и не пишется в журнал.
    count = len(AUDIT)
    res = run(bridge.api_arena(FakeRequest("POST", "players/123456789/wallet", {"currency": "CREDITS", "amount": -5000, "reason": "x"})))
    expect("код ошибки", res.status, 409)
    expect("текст ошибки", json.loads(res.text)["error"], "Недостаточно средств на счёте игрока")
    expect("ошибка без журнала", len(AUDIT), count)

    # --- панель подключена ---
    html = (ROOT / "webapp" / "static" / "admin.html").read_text(encoding="utf-8")
    expect("скрипт в панели", "/admin-assets/arena.js" in html, True)
    settings_js = (ROOT / "webapp" / "static" / "admin" / "settings.js").read_text(encoding="utf-8")
    expect("пункт в «Ещё» только для владельца", '["arena", "game", "Арена"' in settings_js and '"Дурак онлайн: игроки, деньги, турниры", true' in settings_js, True)
    server = (ROOT / "webapp" / "server.py").read_text(encoding="utf-8")
    expect("маршруты на сервере", "setup_arena_admin_routes(app)" in server, True)

    if failures:
        print(f"❌ {len(failures)} проблем:\n")
        print("\n".join(failures))
        return 1
    print(f"✅ Все {checks} проверок раздела «Арена» в панели прошли.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
