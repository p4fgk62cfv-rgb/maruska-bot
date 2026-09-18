import os
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

bot = Bot(token=TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "Привет! Я Маруська 💜\n"
        "Я уже здесь. Скоро научусь общаться, запоминать контекст, "
        "играть и помогать вашей группе 😏"
    )


@dp.message(Command("help"))
async def help_command(message: Message):
    await message.answer(
        "Команды Маруськи:\n"
        "/start — запустить бота\n"
        "/help — помощь\n"
        "/ping — проверить, работаю ли я"
    )


@dp.message(Command("ping"))
async def ping(message: Message):
    await message.answer("Маруська на связи 🟢")


async def main():
    print("Маруська запущена!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
