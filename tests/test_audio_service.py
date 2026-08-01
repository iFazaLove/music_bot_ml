import asyncio
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from music_bot.services import audio as audio_service
from music_bot.services.metadata import ExtractedMetadata


class FakeBot:
    async def download(self, audio: Any, destination: Path) -> None:
        destination.write_bytes(b"temporary audio data")


def test_prepare_track_uses_tags_and_removes_temporary_file(tmp_path, monkeypatch) -> None:
    telegram_audio = SimpleNamespace(
        file_id="file-id",
        file_unique_id="unique-id",
        file_name="track.mp3",
        title="Telegram title",
        performer="Telegram artist",
        duration=120,
        file_size=1024,
    )
    monkeypatch.setattr(
        audio_service,
        "extract_metadata",
        lambda path: ExtractedMetadata(
            title="Tag title",
            artist="Tag artist",
            album="Tag album",
            duration=121.5,
        ),
    )

    pending = asyncio.run(audio_service.prepare_track(FakeBot(), telegram_audio, temp_dir=tmp_path))

    assert pending.title == "Tag title"
    assert pending.artist == "Tag artist"
    assert pending.album == "Tag album"
    assert pending.duration == 121.5
    assert pending.content_hash == sha256(b"temporary audio data").hexdigest()
    assert list(tmp_path.iterdir()) == []


def test_resolve_metadata_keeps_missing_values_for_manual_input() -> None:
    telegram_audio = SimpleNamespace(
        file_id="file-id",
        file_unique_id="unique-id",
        title=None,
        performer=None,
        duration=60,
        file_size=None,
    )

    pending = audio_service.resolve_metadata(
        telegram_audio,
        ExtractedMetadata(),
        content_hash="a" * 64,
    )

    assert pending.title is None
    assert pending.artist is None
    assert pending.duration == 60.0
    assert pending.content_hash == "a" * 64
