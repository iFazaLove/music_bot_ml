import asyncio
import os
from io import BytesIO
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import BotCommand, CallbackQuery, FSInputFile, Message
from aiohttp.client_exceptions import ClientPayloadError
from sqlalchemy import select

from apps.bot.init_db import init_db
from apps.bot.keyboards import (
    build_like_toggle_kb,
    build_my_keyboard,
    build_search_keyboard,
)
from core.audio.metadata import extract_metadata
from core.config.settings import settings
from core.db.base import get_session
from core.db.models import Like, Track, User
from core.db.queries import (
    fetch_user_liked_tracks,
    fetch_user_liked_tracks_by_query,
    get_liked_track_ids,
    get_or_create_user,
    get_track_by_storage_path,
    get_user_by_tg_id,
    get_user_track_by_id,
    is_track_liked_by_user,
    search_tracks_global,
)

bot = Bot(token=settings.tg_token, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

PAGE_LIMIT = 5  # по ТЗ — 5 треков на страницу


def _start_menu_text() -> str:
    return (
        "Доступные команды:\n"
        "• /my — список твоих треков (пагинация и поиск)\n"
        "• Отправь аудио файлом — я сохраню его и добавлю в библиотеку\n"
    )


async def set_commands(bot: Bot) -> None:
    commands = [
        BotCommand(command="start", description="Начало работы"),
        BotCommand(command="my", description="Мои треки"),
        BotCommand(command="search", description="Глобальный поиск"),
    ]
    await bot.set_my_commands(commands)


async def _download_file_bytes(file_id: str, retries: int = 3) -> bytes:
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            file = await bot.get_file(file_id)
            buf = BytesIO()
            await bot.download(file, destination=buf)
            raw = buf.getvalue()
            if not raw:
                raise ValueError("Empty file content")
            return raw
        except (ClientPayloadError, asyncio.TimeoutError, ValueError) as e:
            last_exc = e
            await asyncio.sleep(0.3 * attempt)
            continue
        except Exception as e:
            last_exc = e
            await asyncio.sleep(0.3 * attempt)
    assert last_exc is not None
    raise last_exc


@dp.message(Command("start"))
async def cmd_start(m: Message) -> None:
    # лениво создаём таблицы при первом запуске
    init_db()

    tg_user = m.from_user
    if not tg_user:
        await m.answer("Не удалось получить информацию о пользователе.")
        return

    with get_session() as s:
        existing: Optional[User] = get_user_by_tg_id(s, tg_user.id)
        if existing is None:
            _ = get_or_create_user(s, tg_user.id, tg_user.username)
            await m.answer("Добро пожаловать! Я зарегистрировал тебя ✅\n\n" + _start_menu_text())
        else:
            await m.answer("Ты уже зарегистрирован. 👌\n\n" + _start_menu_text())


@dp.message(F.audio)
async def handle_audio(m: Message) -> None:
    # 1) проверка пользователя
    tg_user = m.from_user
    if tg_user is None:
        await m.answer("Не удалось определить пользователя.")
        return

    # 2) сузим тип: mypy не знает, что audio точно не None
    if m.audio is None:
        await m.answer("Пришлите аудио как файл (тип Audio).")
        return
    audio = m.audio

    # 3) скачиваем файл из TG с ретраями
    try:
        raw = await _download_file_bytes(audio.file_id, retries=3)
    except Exception:
        await m.answer("Не удалось скачать файл. Попробуйте ещё раз.")
        return

    # 4) имя и путь
    ext = (audio.file_name or "audio.mp3").split(".")[-1].lower()
    if len(ext) > 5:
        ext = "mp3"
    folder = os.path.join("data", "tracks", str(tg_user.id))
    os.makedirs(folder, exist_ok=True)
    filename = f"{audio.file_unique_id}.{ext}"
    abs_path = os.path.join(folder, filename)

    # 5) пишем файл (перезапишем, если уже существует)
    with open(abs_path, "wb") as f:
        f.write(raw)

    # 6) метаданные
    meta = extract_metadata(raw)
    title = meta.get("title") or audio.title or "Unknown title"
    artist = meta.get("artist") or audio.performer or "Unknown artist"

    # 7) upsert пользователя и запись трека с учётом дублей по storage_path
    with get_session() as s:
        user = get_or_create_user(s, tg_user.id, tg_user.username)
        created_new = False
        track = get_track_by_storage_path(s, abs_path)
        if track is None:
            track = Track(
                storage_path=abs_path,
                title=title,
                artist=artist,
                album=meta.get("album"),
                duration=meta.get("duration"),
                bitrate=meta.get("bitrate"),
                size=len(raw),
                uploader_user_id=user.id,
            )
            s.add(track)
            s.commit()
            s.refresh(track)
            created_new = True

        # Авто-лайк, если ещё не лайкнут
        liked_added = False
        if not is_track_liked_by_user(s, user.id, track.id):
            s.add(Like(user_id=user.id, track_id=track.id, source="auto_upload"))
            track.likes_count = (track.likes_count or 0) + 1
            s.commit()
            liked_added = True

        track_id = track.id

    if created_new:
        head = "Сохранил"
    else:
        head = "Трек уже был —"
    like_line = (
        "Добавил в избранное ❤️ (можно снять лайк в /my)"
        if liked_added
        else "Уже в избранном ❤️ (можно снять лайк в /my)"
    )
    await m.answer(
        f"{head}: <b>{artist} — {title}</b>\n" f"{like_line}" f"\nID трека: <code>{track_id}</code>"
    )


@dp.message(Command("my"))
async def cmd_my(m: Message) -> None:
    tg_user = m.from_user
    if tg_user is None:
        await m.answer("Не удалось определить пользователя.")
        return

    # извлекаем поисковую фразу, если дана: "/my beatles"
    parts = (m.text or "").split(maxsplit=1)
    query: Optional[str] = parts[1].strip() if len(parts) == 2 else None
    offset = 0

    with get_session() as s:
        user = get_user_by_tg_id(s, tg_user.id)
        if user is None:
            await m.answer("Пользователь не найден.")
            return

        if query:
            items, has_more = fetch_user_liked_tracks_by_query(
                s, user.id, query, offset, PAGE_LIMIT
            )
            header = f"Избранные треки (поиск: <i>{query}</i>):"
        else:
            items, has_more = fetch_user_liked_tracks(s, user.id, offset, PAGE_LIMIT)
            header = "Избранные треки:"

        if not items:
            await m.answer("Пока пусто — добавь первый трек или поставь лайк на существующий.")
            return

        await m.answer(
            header,
            reply_markup=build_my_keyboard(items, offset, PAGE_LIMIT, has_more, query),
            disable_web_page_preview=True,
        )


@dp.callback_query(F.data.startswith("my:page:"))
async def cb_page(query: CallbackQuery) -> None:
    await query.answer()  # быстрый ACK, чтобы не протухло

    data = query.data or ""
    try:
        _, _, off, q = data.split(":", 3)
        offset = int(off)
        search = None if q == "-" else q
    except Exception:
        await query.answer("Некорректная пагинация.", show_alert=True)
        return

    # сузить тип message
    msg = query.message
    if not isinstance(msg, Message):
        await query.answer("Сообщение недоступно.", show_alert=True)
        return

    tg_user = query.from_user
    if tg_user is None:
        await query.answer("Нет пользователя.", show_alert=True)
        return

    with get_session() as s:
        user = get_user_by_tg_id(s, tg_user.id)
        if user is None:
            await query.answer("Пользователь не найден.", show_alert=True)
            return

        if search:
            items, has_more = fetch_user_liked_tracks_by_query(
                s, user.id, search, offset, PAGE_LIMIT
            )
            header = f"Избранные треки (поиск: <i>{search}</i>):"
        else:
            items, has_more = fetch_user_liked_tracks(s, user.id, offset, PAGE_LIMIT)
            header = "Избранные треки:"

        if not items and offset > 0:
            await query.answer("Страница пустая.", show_alert=True)
            return

        try:
            await msg.edit_text(
                header,
                reply_markup=build_my_keyboard(items, offset, PAGE_LIMIT, has_more, search),
                disable_web_page_preview=True,
            )
        except Exception:
            await msg.edit_reply_markup(
                reply_markup=build_my_keyboard(items, offset, PAGE_LIMIT, has_more, search)
            )


@dp.callback_query(F.data.startswith("my:play:"))
async def cb_play(query: CallbackQuery) -> None:
    await query.answer("Отправляю…", cache_time=1)

    data = query.data or ""
    try:
        track_id = int(data.split(":")[2])
    except Exception:
        await query.answer("Некорректный трек.", show_alert=True)
        return

    msg = query.message
    if not isinstance(msg, Message):
        await query.answer("Сообщение недоступно.", show_alert=True)
        return

    tg_user = query.from_user
    if tg_user is None:
        await query.answer("Нет пользователя.", show_alert=True)
        return

    with get_session() as s:
        user = get_user_by_tg_id(s, tg_user.id)
        if user is None:
            await query.answer("Пользователь не найден.", show_alert=True)
            return

        track = get_user_track_by_id(s, user.id, track_id)
        if track is None:
            await query.answer("Трек не найден.", show_alert=True)
            return

        try:
            audio = FSInputFile(track.storage_path)
        except Exception:
            await query.answer("Файл отсутствует.", show_alert=True)
            return

        liked_now = is_track_liked_by_user(s, user.id, track.id)
        caption = f"{track.artist or 'Unknown'} — {track.title or 'Untitled'}  (ID: {track.id})"
        await msg.answer_audio(
            audio=audio,
            caption=caption,
            reply_markup=build_like_toggle_kb(track.id, liked_now, ctx="s", offset=0, query=None),
        )


@dp.callback_query(F.data == "my:close")
async def cb_close(query: CallbackQuery) -> None:
    await query.answer()
    msg = query.message
    if isinstance(msg, Message):
        try:
            await msg.delete()
        except Exception:
            await msg.edit_reply_markup(reply_markup=None)


def _parse_search_input(text: str) -> tuple[str | None, str | None, str, str, str]:
    """Parse /search text into components.
    Returns (search_q, display_q, artist, title, sort)
    - display_q: raw query text without the command prefix (can include filters)
    - sort: 'recent' or 'popular'
    """
    raw = (text or "").strip()
    if raw.startswith("/search"):
        raw = raw[len("/search") :].strip()
    tokens = raw.split()
    artist = ""
    title = ""
    sort = "recent"
    free_tokens: list[str] = []
    for token in tokens:
        low = token.lower()
        if low.startswith("artist:"):
            artist = token.split(":", 1)[1]
        elif low.startswith("title:"):
            title = token.split(":", 1)[1]
        elif low.startswith("sort:"):
            s = token.split(":", 1)[1].lower()
            if s in {"recent", "popular"}:
                sort = s
        elif low.startswith("tag:"):
            # not implemented yet
            pass
        else:
            free_tokens.append(token)
    q = " ".join(free_tokens).strip() or None
    display_q = raw or (q if q else None)
    return q, display_q, artist, title, sort


@dp.message(Command("search"))
async def cmd_search(m: Message) -> None:
    q, display_q, artist, title, sort = _parse_search_input(m.text or "")
    if not (q or artist or title):
        await m.answer(
            "Использование: /search запрос | artist:... | title:... | sort:recent|popular\n"
            "Примеры: /search beatles, /search artist:beatles title:yesterday sort:popular"
        )
        return

    offset = 0
    with get_session() as s:
        user = get_or_create_user(
            s,
            m.from_user.id if m.from_user else 0,
            m.from_user.username if m.from_user else None,
        )
        items, has_more = search_tracks_global(s, q, artist, title, offset, PAGE_LIMIT, sort)
        if not items:
            await m.answer("Ничего не найдено. Попробуй уточнить запрос.")
            return
        liked_ids = get_liked_track_ids(s, user.id, [t.id for t in items])
        header = f"Найдено по: <i>{display_q}</i> (сортировка: {sort})"
        await m.answer(
            header,
            reply_markup=build_search_keyboard(
                items, liked_ids, offset, PAGE_LIMIT, has_more, display_q, sort
            ),
            disable_web_page_preview=True,
        )


@dp.callback_query(F.data.startswith("search:page:"))
async def cb_search_page(query: CallbackQuery) -> None:
    await query.answer()
    data = query.data or ""
    try:
        # format: search:page:<offset>:q:<q>:s:<sort>
        parts = data.split(":")
        offset = int(parts[2])
        params: dict[str, str] = {}
        i = 3
        while i + 1 < len(parts):
            params[parts[i]] = parts[i + 1]
            i += 2
        q_raw = params.get("q", "-")
        sort = params.get("s", "recent")
        q, display_q, artist, title, sort2 = _parse_search_input(q_raw)
        sort = sort or sort2
    except Exception:
        await query.answer("Некорректные данные.", show_alert=True)
        return

    msg = query.message
    if not isinstance(msg, Message):
        return

    with get_session() as s:
        user = get_or_create_user(
            s,
            query.from_user.id if query.from_user else 0,
            query.from_user.username if query.from_user else None,
        )
        items, has_more = search_tracks_global(s, q, artist, title, offset, PAGE_LIMIT, sort)
        if not items and offset > 0:
            offset = max(0, offset - PAGE_LIMIT)
            items, has_more = search_tracks_global(s, q, artist, title, offset, PAGE_LIMIT, sort)
        liked_ids = get_liked_track_ids(s, user.id, [t.id for t in items])
        header = f"Найдено по: <i>{display_q}</i> (сортировка: {sort})"
        try:
            await msg.edit_text(
                header,
                reply_markup=build_search_keyboard(
                    items, liked_ids, offset, PAGE_LIMIT, has_more, display_q, sort
                ),
                disable_web_page_preview=True,
            )
        except Exception:
            await msg.edit_reply_markup(
                reply_markup=build_search_keyboard(
                    items, liked_ids, offset, PAGE_LIMIT, has_more, display_q, sort
                )
            )


@dp.callback_query(F.data.startswith("search:play:"))
async def cb_search_play(query: CallbackQuery) -> None:
    await query.answer("Отправляю…", cache_time=1)
    data = query.data or ""
    try:
        track_id = int(data.split(":")[2])
    except Exception:
        await query.answer("Некорректный трек.", show_alert=True)
        return
    msg = query.message
    if not isinstance(msg, Message):
        return
    with get_session() as s:
        track = s.get(Track, track_id)
        if track is None:
            await query.answer("Трек не найден.", show_alert=True)
            return
        try:
            audio = FSInputFile(track.storage_path)
        except Exception:
            await query.answer("Файл отсутствует.", show_alert=True)
            return
        caption = f"{track.artist or 'Unknown'} — {track.title or 'Untitled'}  (ID: {track.id})"
        await msg.answer_audio(audio=audio, caption=caption)


@dp.callback_query(F.data.startswith("search:like:"))
async def cb_search_like(query: CallbackQuery) -> None:
    data = query.data or ""
    parts = data.split(":")
    try:
        # search:like:<trackId>:off:<offset>:q:<q>:s:<sort>
        track_id = int(parts[2])
        params: dict[str, str] = {}
        i = 3
        while i + 1 < len(parts):
            params[parts[i]] = parts[i + 1]
            i += 2
        offset = int(params.get("off", "0"))
        q_raw = params.get("q", "-")
        sort = params.get("s", "recent")
        q, display_q, artist, title, sort2 = _parse_search_input(q_raw)
        sort = sort or sort2
    except Exception:
        await query.answer("Некорректные данные.", show_alert=True)
        return

    msg = query.message
    if not isinstance(msg, Message):
        return

    with get_session() as s:
        user = get_or_create_user(
            s,
            query.from_user.id if query.from_user else 0,
            query.from_user.username if query.from_user else None,
        )
        track = s.get(Track, track_id)
        if track is None:
            await query.answer("Трек не найден.", show_alert=True)
            return
        liked = is_track_liked_by_user(s, user.id, track.id)
        if not liked:
            s.add(Like(user_id=user.id, track_id=track.id, source="manual"))
            track.likes_count = (track.likes_count or 0) + 1
            s.commit()
            toast = "Добавлено в избранное ❤️"
        else:
            like_obj = s.execute(
                select(Like).where(Like.user_id == user.id, Like.track_id == track.id)
            ).scalar_one_or_none()
            if like_obj is not None:
                s.delete(like_obj)
                track.likes_count = max(0, (track.likes_count or 0) - 1)
                s.commit()
            toast = "Удалено из избранного 💔"

        await query.answer(toast)

        items, has_more = search_tracks_global(s, q, artist, title, offset, PAGE_LIMIT, sort)
        if not items and offset > 0:
            offset = max(0, offset - PAGE_LIMIT)
            items, has_more = search_tracks_global(s, q, artist, title, offset, PAGE_LIMIT, sort)
        liked_ids = get_liked_track_ids(s, user.id, [t.id for t in items])
        header = f"Найдено по: <i>{display_q}</i> (сортировка: {sort})"
        try:
            await msg.edit_text(
                header,
                reply_markup=build_search_keyboard(
                    items, liked_ids, offset, PAGE_LIMIT, has_more, display_q, sort
                ),
                disable_web_page_preview=True,
            )
        except Exception:
            await msg.edit_reply_markup(
                reply_markup=build_search_keyboard(
                    items, liked_ids, offset, PAGE_LIMIT, has_more, display_q, sort
                )
            )


@dp.callback_query(F.data == "search:close")
async def cb_search_close(query: CallbackQuery) -> None:
    await query.answer()
    msg = query.message
    if isinstance(msg, Message):
        try:
            await msg.delete()
        except Exception:
            await msg.edit_reply_markup(reply_markup=None)


@dp.callback_query(F.data.startswith("like:"))
async def cb_like_toggle(query: CallbackQuery) -> None:
    data = query.data or ""
    parts = data.split(":")
    # like:t:<id>:o:<ctx>:p:<offset>:q:<q>
    try:
        params: dict[str, str] = {}
        i = 1
        while i + 1 < len(parts):
            params[parts[i]] = parts[i + 1]
            i += 2
        track_id = int(params.get("t", "0"))
        ctx = params.get("o", "s")
        offset = int(params.get("p", "0"))
        q_raw = params.get("q", "-")
        search = None if q_raw == "-" else q_raw
    except Exception:
        await query.answer("Некорректные данные.", show_alert=True)
        return

    tg_user = query.from_user
    if tg_user is None:
        await query.answer("Нет пользователя.", show_alert=True)
        return

    msg = query.message
    if not isinstance(msg, Message):
        await query.answer("Сообщение недоступно.", show_alert=True)
        return

    with get_session() as s:
        user = get_or_create_user(s, tg_user.id, tg_user.username)
        track = s.get(Track, track_id)
        if track is None:
            await query.answer("Трек не найден.", show_alert=True)
            return

        liked = is_track_liked_by_user(s, user.id, track.id)
        if not liked:
            s.add(Like(user_id=user.id, track_id=track.id, source="manual"))
            track.likes_count = (track.likes_count or 0) + 1
            s.commit()
            liked = True
            toast = "Добавлено в избранное ❤️"
        else:
            like_obj = s.execute(
                select(Like).where(Like.user_id == user.id, Like.track_id == track.id)
            ).scalar_one_or_none()
            if like_obj is not None:
                s.delete(like_obj)
                track.likes_count = max(0, (track.likes_count or 0) - 1)
                s.commit()
            liked = False
            toast = "Удалено из избранного 💔"

        await query.answer(toast)

        if ctx == "m":
            if search:
                items, has_more = fetch_user_liked_tracks_by_query(
                    s, user.id, search, offset, PAGE_LIMIT
                )
                header = f"Избранные треки (поиск: <i>{search}</i>):"
            else:
                items, has_more = fetch_user_liked_tracks(s, user.id, offset, PAGE_LIMIT)
                header = "Избранные треки:"

            if not items and offset > 0:
                offset = max(0, offset - PAGE_LIMIT)
                if search:
                    items, has_more = fetch_user_liked_tracks_by_query(
                        s, user.id, search, offset, PAGE_LIMIT
                    )
                    header = f"Избранные треки (поиск: <i>{search}</i>):"
                else:
                    items, has_more = fetch_user_liked_tracks(s, user.id, offset, PAGE_LIMIT)
                    header = "Избранные треки:"

            try:
                await msg.edit_text(
                    header,
                    reply_markup=build_my_keyboard(items, offset, PAGE_LIMIT, has_more, search),
                    disable_web_page_preview=True,
                )
            except Exception:
                await msg.edit_reply_markup(
                    reply_markup=build_my_keyboard(items, offset, PAGE_LIMIT, has_more, search)
                )
        else:
            await msg.edit_reply_markup(
                reply_markup=build_like_toggle_kb(track.id, liked, ctx="s", offset=0, query=None)
            )


async def start() -> None:
    await set_commands(bot)
    await dp.start_polling(bot)


def main() -> None:
    asyncio.run(start())


if __name__ == "__main__":
    main()
