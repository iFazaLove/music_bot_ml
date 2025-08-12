# apps/bot/main.py
import asyncio
import os
from io import BytesIO
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import select

from apps.bot.init_db import init_db
from core.audio.metadata import extract_metadata
from core.config.settings import settings
from core.db.base import get_session
from core.db.models import Track, User

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


def main() -> None:
    asyncio.run(dp.start_polling(bot))


if __name__ == "__main__":
    main()
