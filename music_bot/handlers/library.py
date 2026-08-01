from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from music_bot.database import SessionFactory, session_scope
from music_bot.models import Track
from music_bot.repositories import (
    add_track_to_library,
    get_library_track_ids,
    get_liked_track_ids,
    get_or_create_user,
    get_track_by_id,
    get_user_library,
    search_tracks,
    toggle_track_like,
)
from music_bot.services.recommendations import recommend_tracks

router = Router(name="library")


def _track_name(track: Track) -> str:
    name = f"{track.artist} — {track.title}"
    return name if len(name) <= 60 else f"{name[:57]}..."


def _tracks_keyboard(
    tracks: list[Track],
    liked_track_ids: set[int],
    library_track_ids: set[int] | None = None,
    show_add_button: bool = False,
) -> InlineKeyboardMarkup:
    library_track_ids = library_track_ids or set()
    rows: list[list[InlineKeyboardButton]] = []
    for track in tracks:
        row = [
            InlineKeyboardButton(
                text=f"▶️ {_track_name(track)}",
                callback_data=f"track:play:{track.id}",
            ),
            InlineKeyboardButton(
                text="❤️" if track.id in liked_track_ids else "🤍",
                callback_data=f"track:like:{track.id}",
            ),
        ]
        if show_add_button:
            row.append(
                InlineKeyboardButton(
                    text="✅" if track.id in library_track_ids else "➕",
                    callback_data=f"track:add:{track.id}",
                )
            )
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _update_like_button(
    markup: InlineKeyboardMarkup,
    callback_data: str,
    liked: bool,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for row in markup.inline_keyboard:
        updated_row = []
        for button in row:
            if button.callback_data == callback_data:
                button = button.model_copy(update={"text": "❤️" if liked else "🤍"})
            updated_row.append(button)
        rows.append(updated_row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _mark_track_as_added(
    markup: InlineKeyboardMarkup,
    callback_data: str,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for row in markup.inline_keyboard:
        updated_row = []
        for button in row:
            if button.callback_data == callback_data:
                button = button.model_copy(update={"text": "✅"})
            updated_row.append(button)
        rows.append(updated_row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("my"))
async def show_library(message: Message, session_factory: SessionFactory) -> None:
    telegram_user = message.from_user
    if telegram_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    with session_scope(session_factory) as session:
        user = get_or_create_user(session, telegram_user.id, telegram_user.username)
        tracks = get_user_library(session, user)
        liked_track_ids = get_liked_track_ids(session, user, tracks)

    if not tracks:
        await message.answer("Твоя библиотека пока пуста. Отправь мне аудиофайл.")
        return

    await message.answer(
        "Последние треки в твоей библиотеке:",
        reply_markup=_tracks_keyboard(tracks, liked_track_ids),
    )


@router.message(Command("search"))
async def search_library(message: Message, session_factory: SessionFactory) -> None:
    parts = (message.text or "").split(maxsplit=1)
    query = parts[1].strip() if len(parts) == 2 else ""
    if not query:
        await message.answer("Укажи название или исполнителя: <code>/search запрос</code>")
        return

    telegram_user = message.from_user
    if telegram_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    with session_scope(session_factory) as session:
        user = get_or_create_user(session, telegram_user.id, telegram_user.username)
        tracks = search_tracks(session, query)
        liked_track_ids = get_liked_track_ids(session, user, tracks)
        library_track_ids = get_library_track_ids(session, user, tracks)

    if not tracks:
        await message.answer(f"По запросу <b>{escape(query)}</b> ничего не найдено.")
        return

    await message.answer(
        f"Результаты поиска по запросу <b>{escape(query)}</b>:",
        reply_markup=_tracks_keyboard(
            tracks,
            liked_track_ids,
            library_track_ids,
            show_add_button=True,
        ),
    )


@router.message(Command("recommend"))
async def show_recommendations(message: Message, session_factory: SessionFactory) -> None:
    telegram_user = message.from_user
    if telegram_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    with session_scope(session_factory) as session:
        user = get_or_create_user(session, telegram_user.id, telegram_user.username)
        tracks = recommend_tracks(session, user)
        liked_track_ids = get_liked_track_ids(session, user, tracks)

    if not tracks:
        await message.answer(
            "Пока нечего рекомендовать. Добавь в общий каталог ещё несколько треков."
        )
        return

    await message.answer(
        "Рекомендации для тебя:",
        reply_markup=_tracks_keyboard(
            tracks,
            liked_track_ids,
            show_add_button=True,
        ),
    )


@router.callback_query(F.data.startswith("track:play:"))
async def send_track(callback: CallbackQuery, session_factory: SessionFactory) -> None:
    try:
        track_id = int((callback.data or "").rsplit(":", maxsplit=1)[1])
    except (IndexError, ValueError):
        await callback.answer("Некорректный ID трека.", show_alert=True)
        return

    with session_scope(session_factory) as session:
        track = get_track_by_id(session, track_id)

    if track is None:
        await callback.answer("Трек больше не найден.", show_alert=True)
        return

    if not isinstance(callback.message, Message):
        await callback.answer("Не удалось отправить трек.", show_alert=True)
        return

    await callback.answer()
    await callback.message.answer_audio(
        audio=track.telegram_file_id,
        caption=f"<b>{escape(track.artist)} — {escape(track.title)}</b>",
    )


@router.callback_query(F.data.startswith("track:like:"))
async def toggle_like(callback: CallbackQuery, session_factory: SessionFactory) -> None:
    try:
        track_id = int((callback.data or "").rsplit(":", maxsplit=1)[1])
    except (IndexError, ValueError):
        await callback.answer("Некорректный ID трека.", show_alert=True)
        return

    with session_scope(session_factory) as session:
        user = get_or_create_user(
            session,
            callback.from_user.id,
            callback.from_user.username,
        )
        track = get_track_by_id(session, track_id)
        liked = toggle_track_like(session, user, track) if track is not None else None

    if liked is None:
        await callback.answer("Трек больше не найден.", show_alert=True)
        return

    await callback.answer("Лайк поставлен ❤️" if liked else "Лайк снят")
    if isinstance(callback.message, Message) and callback.message.reply_markup is not None:
        updated_markup = _update_like_button(
            callback.message.reply_markup,
            callback.data or "",
            liked,
        )
        await callback.message.edit_reply_markup(reply_markup=updated_markup)


@router.callback_query(F.data.startswith("track:add:"))
async def add_to_library(callback: CallbackQuery, session_factory: SessionFactory) -> None:
    try:
        track_id = int((callback.data or "").rsplit(":", maxsplit=1)[1])
    except (IndexError, ValueError):
        await callback.answer("Некорректный ID трека.", show_alert=True)
        return

    with session_scope(session_factory) as session:
        user = get_or_create_user(
            session,
            callback.from_user.id,
            callback.from_user.username,
        )
        track = get_track_by_id(session, track_id)
        added = add_track_to_library(session, user, track) if track is not None else None

    if added is None:
        await callback.answer("Трек больше не найден.", show_alert=True)
        return

    await callback.answer("Трек добавлен в библиотеку" if added else "Трек уже в библиотеке")
    if isinstance(callback.message, Message) and callback.message.reply_markup is not None:
        callback_data = callback.data or ""
        needs_update = any(
            button.callback_data == callback_data and button.text != "✅"
            for row in callback.message.reply_markup.inline_keyboard
            for button in row
        )
        if needs_update:
            updated_markup = _mark_track_as_added(
                callback.message.reply_markup,
                callback_data,
            )
            await callback.message.edit_reply_markup(reply_markup=updated_markup)
