"""
Оплата звёздами Telegram в Маруська Арене.

Счёт создаёт арена (payload «arena:<id заказа>»), а обновления об оплате
Telegram присылает боту — этот модуль передаёт их арене:

  pre_checkout_query  → /api/internal/stars/precheckout  (можно ли платить)
  successful_payment  → /api/internal/stars/paid         (зачислить монеты)

Если арена не ответила на successful_payment, звёзды не теряются: арена
раз в 10 минут сверяет транзакции бота и зачисляет пропущенное сама.

/paysupport и /terms — Telegram требует их от ботов, принимающих оплату.

Настройка та же, что у панели арены: ARENA_URL и ARENA_INTERNAL_SECRET.
"""

import asyncio
import logging
from html import escape

import aiohttp
from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, PreCheckoutQuery

from webapp.arena_admin import arena_secret, arena_url

logger = logging.getLogger(__name__)
router = Router(name="arena_pay")

PREFIX = "arena:"
# Telegram ждёт ответа на pre_checkout_query не больше 10 секунд.
PRECHECKOUT_TIMEOUT = aiohttp.ClientTimeout(total=6)
PAID_TIMEOUT = aiohttp.ClientTimeout(total=10)

SUPPORT_TEXT = (
    "💫 <b>Помощь с оплатой</b>\n\n"
    "Если звёзды списались, а монеты в Арене не появились, подождите 10 минут — "
    "платёж зачислится автоматически.\n\n"
    "Не пришло или нужен возврат — напишите одной строкой:\n"
    "<code>/paysupport что случилось и когда покупали</code>\n"
    "Сообщение получит владелец, проверит и при необходимости вернёт звёзды."
)

TERMS_TEXT = (
    "📄 <b>Условия покупок в Маруська Арене</b>\n\n"
    "• За звёзды Telegram продаются только монеты — игровая валюта для рубашек карт, "
    "рамок, смайлов и подсказок.\n"
    "• Монеты нельзя вывести, обменять на деньги или на кредиты для ставок.\n"
    "• Монеты зачисляются сразу после оплаты (в редких случаях — до 10 минут).\n"
    "• Возврат возможен, если монеты не пришли или ещё не потрачены: /paysupport.\n"
    "• За нарушение правил игры аккаунт могут заблокировать; купленные монеты при этом не возвращаются."
)


async def _arena(path: str, body: dict, timeout: aiohttp.ClientTimeout) -> tuple[int, dict]:
    url = f"{arena_url()}/api/internal/stars/{path}"
    headers = {"Authorization": f"Bearer {arena_secret()}"}
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=body, headers=headers) as response:
                try:
                    data = await response.json(content_type=None)
                except ValueError:
                    data = {}
                return response.status, data if isinstance(data, dict) else {}
    except (aiohttp.ClientError, asyncio.TimeoutError) as error:
        logger.warning("ARENA PAY: %s failed: %s", path, error)
        return 502, {}


def _configured() -> bool:
    return bool(arena_url() and arena_secret())


@router.pre_checkout_query(F.invoice_payload.startswith(PREFIX))
async def arena_precheckout(query: PreCheckoutQuery):
    if not _configured():
        await query.answer(ok=False, error_message="Оплата временно недоступна. Попробуйте позже.")
        return
    status, data = await _arena(
        "precheckout",
        {
            "payload": query.invoice_payload,
            "telegramId": query.from_user.id,
            "stars": query.total_amount,
            "currency": query.currency,
        },
        PRECHECKOUT_TIMEOUT,
    )
    if status == 200 and data.get("ok") is True:
        await query.answer(ok=True)
        return
    message = data.get("message") if status == 200 else None
    await query.answer(ok=False, error_message=message or "Арена не отвечает. Попробуйте через минуту.")


@router.message(F.successful_payment.invoice_payload.startswith(PREFIX))
async def arena_paid(message: Message):
    payment = message.successful_payment
    body = {
        "payload": payment.invoice_payload,
        "telegramId": message.from_user.id,
        "stars": payment.total_amount,
        "chargeId": payment.telegram_payment_charge_id,
    }
    data: dict = {}
    for attempt in range(4):
        status, data = await _arena("paid", body, PAID_TIMEOUT)
        if status == 200:
            break
        if status in (400, 401, 404):
            logger.error("ARENA PAY: paid %s → %s", payment.invoice_payload, status)
            break
        await asyncio.sleep(2 * 2**attempt)
    else:
        status = 502

    if status == 200:
        coins = data.get("coins", 0)
        await message.answer(f"✅ Спасибо за покупку! <b>+{coins} монет</b> уже на вашем счёте в Арене.")
    else:
        await message.answer(
            "✅ Оплата получена. Монеты появятся в Арене в течение 10 минут.\n"
            "Если не появятся — /paysupport."
        )


@router.message(Command("paysupport"))
async def paysupport(message: Message, command: CommandObject):
    text = (command.args or "").strip()
    if not text:
        await message.answer(SUPPORT_TEXT)
        return
    from settings.handler import OWNER_IDS

    user = message.from_user
    who = f'<a href="tg://user?id={user.id}">{escape(user.full_name)}</a>'
    if user.username:
        who += f" (@{escape(user.username)})"
    report = f"💫 <b>Вопрос об оплате</b>\nОт: {who}, id <code>{user.id}</code>\n\n{escape(text[:1500])}"
    delivered = 0
    for owner in OWNER_IDS:
        try:
            await message.bot.send_message(owner, report)
            delivered += 1
        except Exception as error:  # владелец не начал чат с ботом и т. п.
            logger.warning("ARENA PAY: support to %s failed: %s", owner, error)
    if delivered:
        await message.answer("📨 Передано владельцу. Ответ придёт сюда или в личные сообщения.")
    else:
        await message.answer("Не получилось передать сообщение. Попробуйте позже.")


@router.message(Command("terms"))
async def terms(message: Message):
    await message.answer(TERMS_TEXT)
