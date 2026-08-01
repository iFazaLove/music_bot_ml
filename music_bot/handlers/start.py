from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from music_bot.database import SessionFactory, session_scope
from music_bot.repositories import get_or_create_user

router = Router(name="start")


@router.message(CommandStart())
async def handle_start(message: Message, session_factory: SessionFactory) -> None:
    telegram_user = message.from_user
    if telegram_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    with session_scope(session_factory) as session:
        get_or_create_user(session, telegram_user.id, telegram_user.username)

    await message.answer(
        "Привет! Отправь мне аудиофайл — я прочитаю метаданные и добавлю трек в библиотеку."
    )
