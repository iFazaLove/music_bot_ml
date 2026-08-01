from __future__ import annotations

import argparse
import asyncio
import socket
from pathlib import Path

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramNetworkError
from aiogram.types import FSInputFile, InputProfilePhotoAnimated

from music_bot.config import get_settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AVATAR_PATH = PROJECT_ROOT / "assets" / "branding" / "music-bot-avatar-animated.mp4"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Загрузить анимированный MP4-аватар Telegram-бота.",
    )
    parser.add_argument(
        "avatar",
        nargs="?",
        type=Path,
        default=DEFAULT_AVATAR_PATH,
        help=f"путь к квадратному MP4 (по умолчанию: {DEFAULT_AVATAR_PATH})",
    )
    parser.add_argument(
        "--main-frame-timestamp",
        type=float,
        default=0.0,
        help="кадр в секундах для статичного превью (по умолчанию: 0.0)",
    )
    return parser.parse_args()


def validate_args(avatar_path: Path, main_frame_timestamp: float) -> Path:
    resolved_path = avatar_path.expanduser().resolve()
    if not resolved_path.is_file():
        raise SystemExit(f"Файл аватара не найден: {resolved_path}")
    if resolved_path.suffix.lower() != ".mp4":
        raise SystemExit("Для анимированного аватара нужен файл в формате MP4.")
    if main_frame_timestamp < 0:
        raise SystemExit("Время статичного кадра не может быть отрицательным.")
    return resolved_path


def create_ipv4_session() -> AiohttpSession:
    session = AiohttpSession()
    # Some VPN/DNS tools return an IPv4-mapped IPv6 address for Telegram.
    # aiohttp can fail on that address, while a direct IPv4 connection works.
    session._connector_init["family"] = socket.AF_INET
    return session


async def upload_avatar(avatar_path: Path, main_frame_timestamp: float) -> None:
    settings = get_settings()
    bot = Bot(token=settings.token, session=create_ipv4_session())
    try:
        avatar = InputProfilePhotoAnimated(
            animation=FSInputFile(avatar_path),
            main_frame_timestamp=main_frame_timestamp,
        )
        await bot.set_my_profile_photo(photo=avatar)
    finally:
        await bot.session.close()


def main() -> None:
    args = parse_args()
    avatar_path = validate_args(args.avatar, args.main_frame_timestamp)
    try:
        asyncio.run(upload_avatar(avatar_path, args.main_frame_timestamp))
    except TelegramNetworkError as error:
        raise SystemExit(
            "Не удалось подключиться к api.telegram.org. Проверь интернет, VPN и прокси, "
            f"затем повтори команду. Детали: {error}"
        ) from None
    print(f"Анимированный аватар загружен: {avatar_path}")


if __name__ == "__main__":
    main()
