from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mutagen import File as MutagenFile
from mutagen import MutagenError


@dataclass(frozen=True, slots=True)
class ExtractedMetadata:
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    duration: float | None = None


def _first_tag(tags: Any, key: str) -> str | None:
    if not tags or key not in tags:
        return None

    value = tags[key]
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def extract_metadata(path: Path) -> ExtractedMetadata:
    try:
        audio = MutagenFile(path, easy=True)
    except (MutagenError, OSError, ValueError):
        return ExtractedMetadata()

    if audio is None:
        return ExtractedMetadata()

    info = getattr(audio, "info", None)
    duration = getattr(info, "length", None)
    tags = getattr(audio, "tags", None)

    return ExtractedMetadata(
        title=_first_tag(tags, "title"),
        artist=_first_tag(tags, "artist"),
        album=_first_tag(tags, "album"),
        duration=float(duration) if duration is not None else None,
    )
