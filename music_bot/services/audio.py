from dataclasses import asdict, dataclass
from hashlib import file_digest
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from aiogram import Bot
from aiogram.types import Audio

from music_bot.services.metadata import ExtractedMetadata, extract_metadata

ALLOWED_SUFFIXES = {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".opus", ".wav"}


@dataclass(frozen=True, slots=True)
class PendingTrack:
    telegram_file_id: str
    telegram_file_unique_id: str
    content_hash: str
    title: str | None
    artist: str | None
    album: str | None
    duration: float | None
    file_size: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PendingTrack":
        return cls(
            telegram_file_id=str(data["telegram_file_id"]),
            telegram_file_unique_id=str(data["telegram_file_unique_id"]),
            content_hash=str(data["content_hash"]),
            title=_clean_text(data.get("title")),
            artist=_clean_text(data.get("artist")),
            album=_clean_text(data.get("album")),
            duration=float(data["duration"]) if data.get("duration") is not None else None,
            file_size=int(data["file_size"]) if data.get("file_size") is not None else None,
        )


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def resolve_metadata(
    audio: Audio,
    extracted: ExtractedMetadata,
    content_hash: str,
) -> PendingTrack:
    return PendingTrack(
        telegram_file_id=audio.file_id,
        telegram_file_unique_id=audio.file_unique_id,
        content_hash=content_hash,
        title=_clean_text(extracted.title) or _clean_text(audio.title),
        artist=_clean_text(extracted.artist) or _clean_text(audio.performer),
        album=_clean_text(extracted.album),
        duration=extracted.duration or float(audio.duration),
        file_size=audio.file_size,
    )


def _safe_suffix(file_name: str | None) -> str:
    suffix = Path(file_name or "").suffix.lower()
    return suffix if suffix in ALLOWED_SUFFIXES else ".audio"


def calculate_content_hash(path: Path) -> str:
    with path.open("rb") as audio_file:
        return file_digest(audio_file, "sha256").hexdigest()


async def prepare_track(
    bot: Bot,
    audio: Audio,
    temp_dir: Path | None = None,
) -> PendingTrack:
    if temp_dir is not None:
        temp_dir.mkdir(parents=True, exist_ok=True)

    with NamedTemporaryFile(
        suffix=_safe_suffix(audio.file_name),
        dir=temp_dir,
        delete=False,
    ) as temporary_file:
        temporary_path = Path(temporary_file.name)

    try:
        await bot.download(audio, destination=temporary_path)
        content_hash = calculate_content_hash(temporary_path)
        extracted = extract_metadata(temporary_path)
        return resolve_metadata(audio, extracted, content_hash)
    finally:
        temporary_path.unlink(missing_ok=True)
