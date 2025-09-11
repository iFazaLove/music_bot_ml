import asyncio
import os
from io import BytesIO
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import BotCommand, CallbackQuery, FSInputFile, Message
from sqlalchemy import select

from apps.bot.init_db import init_db
from apps.bot.keyborads import build_my_keyboard
from core.audio.metadata import extract_metadata
from core.config.settings import settings
from core.db.base import get_session
from core.db.models import Track, User
from core.db.queries import fetch_user_tracks, fetch_user_tracks_by_query

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
    ]
    await bot.set_my_commands(commands)


@dp.message(Command("start"))
async def cmd_start(m: Message) -> None:
    # лениво создаём таблицы при первом запуске
    init_db()

    tg_user = m.from_user
    if not tg_user:
        await m.answer("Не удалось получить информацию о пользователе.")
        return

    for s in get_session():
        existing: Optional[User] = s.execute(
            select(User).where(User.tg_id == tg_user.id)
        ).scalar_one_or_none()

        if existing is None:
            # регаем нового
            u = User(tg_id=tg_user.id, username=tg_user.username)
            s.add(u)
            s.commit()
            await m.answer("Добро пожаловать! Я зарегистрировал тебя ✅\n\n" + _start_menu_text())
        else:
            # уже есть в базе
            await m.answer("Ты уже зарегистрирован. 👌\n\n" + _start_menu_text())
        break


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

    # 3) скачиваем файл из TG
    file = await bot.get_file(audio.file_id)
    buf = BytesIO()
    await bot.download(file, destination=buf)
    raw = buf.getvalue()

    # 4) имя и путь
    ext = (audio.file_name or "audio.mp3").split(".")[-1].lower()
    if len(ext) > 5:
        ext = "mp3"
    folder = os.path.join("data", "tracks", str(tg_user.id))
    os.makedirs(folder, exist_ok=True)
    filename = f"{audio.file_unique_id}.{ext}"
    abs_path = os.path.join(folder, filename)

    # 5) пишем файл
    with open(abs_path, "wb") as f:
        f.write(raw)

    # 6) метаданные
    meta = extract_metadata(raw)
    title = meta.get("title") or audio.title or "Unknown title"
    artist = meta.get("artist") or audio.performer or "Unknown artist"

    # 7) upsert пользователя и запись трека (как у тебя было)
    for s in get_session():
        user = s.execute(select(User).where(User.tg_id == tg_user.id)).scalar_one_or_none()
        if user is None:
            user = User(tg_id=tg_user.id, username=tg_user.username)
            s.add(user)
            s.commit()
            s.refresh(user)

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
        track_id = track.id
        break

    await m.answer(f"Сохранил: <b>{artist} — {title}</b>\nID трека: <code>{track_id}</code>")


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

    for s in get_session():
        user = s.execute(select(User).where(User.tg_id == tg_user.id)).scalar_one_or_none()
        if user is None:
            await m.answer("Пользователь не найден.")
            break

        if query:
            items, has_more = fetch_user_tracks_by_query(s, user.id, query, offset, PAGE_LIMIT)
            header = f"Твои треки (поиск: <i>{query}</i>):"
        else:
            items, has_more = fetch_user_tracks(s, user.id, offset, PAGE_LIMIT)
            header = "Твои треки:"

        if not items:
            await m.answer("Ничего не нашлось." if query else "Пока треков нет.")
            break

        header = f"Твои треки (поиск: <i>{query}</i>)" if query else "Твои треки:"
        await m.answer(
            header,
            reply_markup=build_my_keyboard(items, offset, PAGE_LIMIT, has_more, query),
            disable_web_page_preview=True,
        )
        break


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

    for s in get_session():
        user = s.execute(select(User).where(User.tg_id == tg_user.id)).scalar_one_or_none()
        if user is None:
            await query.answer("Пользователь не найден.", show_alert=True)
            break

        if search:
            items, has_more = fetch_user_tracks_by_query(s, user.id, search, offset, PAGE_LIMIT)
            header = f"Твои треки (поиск: <i>{search}</i>):"
        else:
            items, has_more = fetch_user_tracks(s, user.id, offset, PAGE_LIMIT)
            header = "Твои треки:"

        if not items and offset > 0:
            await query.answer("Страница пустая.", show_alert=True)
            break

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
        break


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

    for s in get_session():
        user = s.execute(select(User).where(User.tg_id == tg_user.id)).scalar_one_or_none()
        if user is None:
            await query.answer("Пользователь не найден.", show_alert=True)
            break

        track = s.execute(
            select(Track).where(Track.id == track_id, Track.uploader_user_id == user.id)
        ).scalar_one_or_none()
        if track is None:
            await query.answer("Трек не найден.", show_alert=True)
            break

        try:
            audio = FSInputFile(track.storage_path)
        except Exception:
            await query.answer("Файл отсутствует.", show_alert=True)
            break

        caption = f"{track.artist or 'Unknown'} — {track.title or 'Untitled'}  (ID: {track.id})"
        await msg.answer_audio(audio=audio, caption=caption)
        break


@dp.callback_query(F.data == "my:close")
async def cb_close(query: CallbackQuery) -> None:
    await query.answer()
    msg = query.message
    if isinstance(msg, Message):
        try:
            await msg.delete()
        except Exception:
            await msg.edit_reply_markup(reply_markup=None)


async def start() -> None:
    await set_commands(bot)
    await dp.start_polling(bot)


def main() -> None:
    asyncio.run(start())


if __name__ == "__main__":
    main()
