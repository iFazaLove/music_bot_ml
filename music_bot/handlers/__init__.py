from aiogram import Router

from music_bot.handlers.library import router as library_router
from music_bot.handlers.start import router as start_router
from music_bot.handlers.upload import router as upload_router


def build_router() -> Router:
    router = Router(name="root")
    router.include_router(start_router)
    router.include_router(library_router)
    router.include_router(upload_router)
    return router
