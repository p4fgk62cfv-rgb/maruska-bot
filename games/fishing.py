"""Telegram Mini App entry point for Maruska Fishing."""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, Message

from webapp.server import public_url

router = Router(name='fishing')
COMMANDS = ['рыбалка', 'рыбачим', 'fish', 'fishing', 'рыбы']

@router.message(Command(commands=COMMANDS))
async def fishing_command(message: Message):
    base = public_url()
    if not base:
        await message.answer('🎣 Рыбалка пока недоступна: у бота не настроен публичный HTTPS-адрес.')
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🎣 Открыть рыбалку', web_app=WebAppInfo(url=f'{base}/fishing'))]
    ])
    await message.answer(
        '🎣 <b>Маруська Fishing</b>\n\nВыбирай водоём, забрасывай удочку, вываживай рыбу и собирай коллекцию.',
        reply_markup=kb,
    )
