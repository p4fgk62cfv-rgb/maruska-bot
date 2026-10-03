"""Защита веб-приложения: подпись initData, срок входа в админку, заголовки.  python test_webapp_security.py"""

import asyncio
import hashlib
import hmac
import json
import os
import pathlib
import sys
import time
from urllib.parse import urlencode

ROOT = pathlib.Path(__file__).parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "postgresql://unused@localhost/unused")

from aiohttp import web  # noqa: E402
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

from webapp.server import ADMIN_AUTH_AGE, SECURITY_HEADERS, security_headers, verify_init_data  # noqa: E402

TOKEN = "123456:TEST-token"
failures, checks = [], 0


def expect(label, got, want):
    global checks
    checks += 1
    if got != want:
        failures.append(f"  {label}: получили {got!r}, ждали {want!r}")


def signed(age: int | None, user_id: int = 42) -> str:
    pairs = {"user": json.dumps({"id": user_id})}
    if age is not None:
        pairs["auth_date"] = str(int(time.time()) - age)
    check = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(pairs)


fresh = signed(60)
expect("свежая подпись", (verify_init_data(fresh, TOKEN) or {}).get("user"), {"id": 42})
expect("чужой токен", verify_init_data(fresh, "999:other"), None)
expect("подделанный пользователь", verify_init_data(fresh.replace("42", "43"), TOKEN), None)
expect("без auth_date", verify_init_data(signed(None), TOKEN), None)
expect("2 часа — игрокам можно", verify_init_data(signed(2 * 3600), TOKEN) is not None, True)
expect("2 часа — админке нельзя", verify_init_data(signed(2 * 3600), TOKEN, max_age=ADMIN_AUTH_AGE), None)
expect("30 минут — админке можно", verify_init_data(signed(1800), TOKEN, max_age=ADMIN_AUTH_AGE) is not None, True)
expect("25 часов — никому", verify_init_data(signed(25 * 3600), TOKEN), None)


async def headers():
    async def ok(request):
        return web.Response(text="ok")

    async def denied(request):
        raise web.HTTPUnauthorized(text="bad signature")

    app = web.Application(middlewares=[security_headers])
    app.router.add_get("/ok", ok)
    app.router.add_get("/denied", denied)
    async with TestClient(TestServer(app)) as client:
        for path in ("/ok", "/denied", "/missing"):
            res = await client.get(path)
            for name, value in SECURITY_HEADERS.items():
                expect(f"{path} {name}", res.headers.get(name), value)


asyncio.run(headers())

if failures:
    print("❌ Ошибки защиты веб-приложения:")
    print("\n".join(failures))
    sys.exit(1)
print(f"✅ Все {checks} проверок защиты веб-приложения прошли.")
