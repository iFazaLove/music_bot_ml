# apps/bot/main.py
import asyncio

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import Message

from core.config.settings import settings

bot = Bot(token=settings.tg_token, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()


@dp.message(Command("start"))
async def cmd_start(m: Message) -> None:
    await m.answer("Привет! Я живой. Напиши /ping.")


@dp.message(Command("ping"))
async def cmd_ping(m: Message) -> None:
    await m.answer("pong 🏓")


@dp.message(F.text)
async def fallback(m: Message) -> None:
    await m.answer("Команда не распознана. Попробуй /start или /ping.")


def main() -> None:
    asyncio.run(dp.start_polling(bot))


if __name__ == "__main__":
    main()
