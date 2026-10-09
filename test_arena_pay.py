"""
Оплата звёздами: бот передаёт pre_checkout_query и successful_payment арене
и отвечает Telegram. Арена заменена поддельным HTTP-сервером.
Запуск:  python test_arena_pay.py
"""

import asyncio
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from aiohttp import web  # noqa: E402

errors = []


def check(ok, what):
    if not ok:
        errors.append(what)


class Query:
    def __init__(self, payload, stars=75, user_id=111):
        self.invoice_payload = payload
        self.total_amount = stars
        self.currency = "XTR"
        self.from_user = type("U", (), {"id": user_id})()
        self.answers = []

    async def answer(self, ok, error_message=None):
        self.answers.append((ok, error_message))


class Msg:
    def __init__(self, payload):
        self.successful_payment = type("P", (), {
            "invoice_payload": payload, "total_amount": 75, "telegram_payment_charge_id": "ch-1",
        })()
        self.from_user = type("U", (), {"id": 111})()
        self.replies = []

    async def answer(self, text, **kwargs):
        self.replies.append(text)


async def main():
    seen = []
    mode = {"precheckout": 200, "paid": 200}

    async def precheckout(request):
        body = await request.json()
        seen.append(("precheckout", body, request.headers.get("Authorization")))
        if mode["precheckout"] != 200:
            return web.json_response({}, status=mode["precheckout"])
        ok = body["payload"] == "arena:good"
        return web.json_response({"ok": True} if ok else {"ok": False, "message": "Счёт не найден."})

    async def paid(request):
        body = await request.json()
        seen.append(("paid", body, None))
        if mode["paid"] != 200:
            return web.json_response({}, status=mode["paid"])
        return web.json_response({"coins": 160, "status": "PAID", "credited": True})

    app = web.Application()
    app.router.add_post("/api/internal/stars/precheckout", precheckout)
    app.router.add_post("/api/internal/stars/paid", paid)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    os.environ["ARENA_URL"] = f"http://127.0.0.1:{port}"
    os.environ["ARENA_INTERNAL_SECRET"] = "s" * 20

    from features import arena_pay

    q = Query("arena:good")
    await arena_pay.arena_precheckout(q)
    check(q.answers == [(True, None)], f"хороший счёт: {q.answers}")
    check(seen[-1][1] == {"payload": "arena:good", "telegramId": 111, "stars": 75, "currency": "XTR"}, f"тело: {seen[-1][1]}")
    check(seen[-1][2] == "Bearer " + "s" * 20, "ключ арены")

    q = Query("arena:bad")
    await arena_pay.arena_precheckout(q)
    check(q.answers == [(False, "Счёт не найден.")], f"плохой счёт: {q.answers}")

    mode["precheckout"] = 500
    q = Query("arena:good")
    await arena_pay.arena_precheckout(q)
    check(q.answers and q.answers[0][0] is False and q.answers[0][1], f"арена упала: {q.answers}")
    mode["precheckout"] = 200

    m = Msg("arena:good")
    await arena_pay.arena_paid(m)
    check(seen[-1][1] == {"payload": "arena:good", "telegramId": 111, "stars": 75, "chargeId": "ch-1"}, f"paid тело: {seen[-1][1]}")
    check(m.replies and "+160" in m.replies[0], f"ответ после оплаты: {m.replies}")

    mode["paid"] = 404
    m = Msg("arena:lost")
    await arena_pay.arena_paid(m)
    check(m.replies and "10 минут" in m.replies[0], f"заказ не найден: {m.replies}")

    os.environ["ARENA_URL"] = ""
    q = Query("arena:good")
    await arena_pay.arena_precheckout(q)
    check(q.answers and q.answers[0][0] is False, "без настройки арены оплата не проходит")

    await runner.cleanup()


asyncio.run(main())
if errors:
    print("❌ " + "\n❌ ".join(errors))
    sys.exit(1)
print("✅ Оплата звёздами: все проверки прошли.")
