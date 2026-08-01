import logging
from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from music_bot.config import Settings
from music_bot.database import SessionFactory, session_scope
from music_bot.repositories import (
    TrackInput,
    add_track_to_library,
    get_or_create_user,
    get_track_by_unique_id,
    save_track,
)
from music_bot.services.audio import PendingTrack, prepare_track

router = Router(name="upload")
logger = logging.getLogger(__name__)


class UploadTrack(StatesGroup):
    waiting_for_title = State()
    waiting_for_artist = State()


def _manual_value(message: Message) -> str | None:
    value = (message.text or "").strip()
    if not value or len(value) > 512:
        return None
    return value


async def _save_pending_track(
    message: Message,
    state: FSMContext,
    session_factory: SessionFactory,
    pending: PendingTrack,
) -> None:
    telegram_user = message.from_user
    if telegram_user is None or pending.title is None or pending.artist is None:
        await message.answer("Не удалось сохранить трек: не хватает данных.")
        return

    track_input = TrackInput(
        telegram_file_id=pending.telegram_file_id,
        telegram_file_unique_id=pending.telegram_file_unique_id,
        content_hash=pending.content_hash,
        title=pending.title,
        artist=pending.artist,
        album=pending.album,
        duration=pending.duration,
        file_size=pending.file_size,
    )

    with session_scope(session_factory) as session:
        uploader = get_or_create_user(session, telegram_user.id, telegram_user.username)
        track, created = save_track(session, uploader, track_input)
        added_to_library = add_track_to_library(session, uploader, track)

    await state.clear()
    if created:
        action = "Сохранил"
    elif added_to_library:
        action = "Добавил существующий трек в твою библиотеку"
    else:
        action = "Этот трек уже есть в твоей библиотеке"
    await message.answer(
        f"{action}: <b>{escape(track.artist)} — {escape(track.title)}</b>\n"
        f"ID трека: <code>{track.id}</code>"
    )


@router.message(Command("cancel"))
async def cancel_upload(message: Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Сейчас нет незавершённой загрузки.")
        return
    await state.clear()
    await message.answer("Загрузка отменена.")


@router.message(UploadTrack.waiting_for_title, F.text)
async def receive_title(
    message: Message,
    state: FSMContext,
    session_factory: SessionFactory,
) -> None:
    title = _manual_value(message)
    if title is None:
        await message.answer("Введи название текстом, не длиннее 512 символов.")
        return

    data = await state.get_data()
    pending = PendingTrack.from_dict(data["pending_track"])
    pending = PendingTrack(**{**pending.to_dict(), "title": title})

    if pending.artist is None:
        await state.update_data(pending_track=pending.to_dict())
        await state.set_state(UploadTrack.waiting_for_artist)
        await message.answer("Исполнитель тоже не найден. Введи его вручную.")
        return

    await _save_pending_track(message, state, session_factory, pending)


@router.message(UploadTrack.waiting_for_title)
async def require_title_text(message: Message) -> None:
    await message.answer("Ожидаю название трека текстом. Для отмены используй /cancel.")


@router.message(UploadTrack.waiting_for_artist, F.text)
async def receive_artist(
    message: Message,
    state: FSMContext,
    session_factory: SessionFactory,
) -> None:
    artist = _manual_value(message)
    if artist is None:
        await message.answer("Введи исполнителя текстом, не длиннее 512 символов.")
        return

    data = await state.get_data()
    pending = PendingTrack.from_dict(data["pending_track"])
    pending = PendingTrack(**{**pending.to_dict(), "artist": artist})
    await _save_pending_track(message, state, session_factory, pending)


@router.message(UploadTrack.waiting_for_artist)
async def require_artist_text(message: Message) -> None:
    await message.answer("Ожидаю имя исполнителя текстом. Для отмены используй /cancel.")


@router.message(F.audio)
async def receive_audio(
    message: Message,
    state: FSMContext,
    session_factory: SessionFactory,
    settings: Settings,
) -> None:
    telegram_user = message.from_user
    audio = message.audio
    if telegram_user is None or audio is None:
        await message.answer("Не удалось получить аудиофайл.")
        return

    with session_scope(session_factory) as session:
        user = get_or_create_user(session, telegram_user.id, telegram_user.username)
        existing = get_track_by_unique_id(session, audio.file_unique_id)
        if existing is not None:
            existing.telegram_file_id = audio.file_id
            added_to_library = add_track_to_library(session, user, existing)
            track_title = existing.title
            track_artist = existing.artist
            track_id = existing.id
        else:
            added_to_library = False
            track_title = None
            track_artist = None
            track_id = None

    if track_id is not None:
        await state.clear()
        action = (
            "Добавил существующий трек в твою библиотеку"
            if added_to_library
            else "Этот трек уже есть в твоей библиотеке"
        )
        await message.answer(
            f"{action}: "
            f"<b>{escape(track_artist or '')} — {escape(track_title or '')}</b>\n"
            f"ID трека: <code>{track_id}</code>"
        )
        return

    await message.answer("Читаю метаданные…")
    try:
        pending = await prepare_track(message.bot, audio, settings.temp_dir)
    except Exception:
        logger.exception("Failed to download or read Telegram audio")
        await message.answer("Не удалось обработать файл. Попробуй отправить другое аудио.")
        return

    if pending.title is None:
        await state.update_data(pending_track=pending.to_dict())
        await state.set_state(UploadTrack.waiting_for_title)
        await message.answer("Название не найдено. Введи его вручную.")
        return

    if pending.artist is None:
        await state.update_data(pending_track=pending.to_dict())
        await state.set_state(UploadTrack.waiting_for_artist)
        await message.answer("Исполнитель не найден. Введи его вручную.")
        return

    await _save_pending_track(message, state, session_factory, pending)
