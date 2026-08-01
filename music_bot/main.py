import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from music_bot.config import get_settings
from music_bot.database import create_database, init_database
from music_bot.handlers import build_router


async def run_bot() -> None:
    settings = get_settings()
    engine, session_factory = create_database(settings.database_url)
    init_database(engine)

    bot = Bot(
        token=settings.token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(build_router())

    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Начать работу"),
            BotCommand(command="my", description="Моя библиотека"),
            BotCommand(command="search", description="Найти трек"),
            BotCommand(command="recommend", description="Рекомендации"),
            BotCommand(command="cancel", description="Отменить загрузку"),
        ]
    )

    try:
        await dispatcher.start_polling(
            bot,
            session_factory=session_factory,
            settings=settings,
        )
    finally:
        engine.dispose()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
