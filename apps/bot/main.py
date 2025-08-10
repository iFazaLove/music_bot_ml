# apps/bot/main.py
import asyncio
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import select

from apps.bot.init_db import init_db
from core.config.settings import settings
from core.db.base import get_session
from core.db.models import User

bot = Bot(token=settings.tg_token, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()


@dp.message(Command("start"))
async def cmd_start(m: Message) -> None:
    # лениво создаём таблицы при первом запуске
    init_db()

    tg_user = m.from_user
    if not tg_user:
        await m.answer("Не удалось получить информацию о пользователе.")
        return

    uid = tg_user.id
    username: Optional[str] = tg_user.username

    # upsert пользователя
    for s in get_session():
        user = s.execute(select(User).where(User.tg_id == uid)).scalar_one_or_none()
        if not user:
            user = User(tg_id=uid, username=username)
            s.add(user)
            s.commit()
        break

    await m.answer("Привет! Я сохранил тебя в базе. Напиши /ping.")


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
