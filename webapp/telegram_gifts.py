"""Small Bot API client for Telegram Gifts.

Uses the HTTPS Bot API directly so the Control Center remains compatible
with the pinned aiogram version in the bot project even when Telegram adds
new gift fields before aiogram exposes them.
"""
import httpx


async def call(token: str, method: str, payload: dict | None = None) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(url, json=payload or {})
        response.raise_for_status()
        data = response.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("description") or f"Telegram API error: {method}")
    return data.get("result") or {}


async def available_gifts(token: str) -> list[dict]:
    result = await call(token, "getAvailableGifts")
    return result.get("gifts", [])


async def star_balance(token: str) -> int:
    result = await call(token, "getMyStarBalance")
    return int(result.get("amount", 0))


async def send_gift(token: str, *, user_id: int, gift_id: str,
                    pay_for_upgrade: bool = False, text: str = "") -> dict:
    payload = {"user_id": user_id, "gift_id": gift_id}
    if pay_for_upgrade:
        payload["pay_for_upgrade"] = True
    if text:
        payload["text"] = text[:128]
    return await call(token, "sendGift", payload)


async def star_transactions(token: str, limit: int = 50) -> list[dict]:
    result = await call(token, "getStarTransactions", {"limit": max(1, min(limit, 100))})
    return result.get("transactions", [])
