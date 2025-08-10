from io import BytesIO
from typing import Any

from mutagen import File as MutagenFile


def extract_metadata(raw: bytes) -> dict[str, Any]:
    f = MutagenFile(BytesIO(raw))
    if f is None:
        return {}

    info = getattr(f, "info", None)
    duration = getattr(info, "length", None)
    bitrate = getattr(info, "bitrate", None)

    title = None
    artist = None
    album = None
    tags = getattr(f, "tags", None) or {}

    # Популярные ключи для mp3/m4a/ogg
    for k in ("TIT2", "title", "\xa9nam"):
        if k in tags:
            v = tags[k]
            title = str(v[0] if isinstance(v, list) else v)
            break
    for k in ("TPE1", "artist", "\xa9ART"):
        if k in tags:
            v = tags[k]
            artist = str(v[0] if isinstance(v, list) else v)
            break
    for k in ("TALB", "album", "\xa9alb"):
        if k in tags:
            v = tags[k]
            album = str(v[0] if isinstance(v, list) else v)
            break

    return {
        "title": title,
        "artist": artist,
        "album": album,
        "duration": float(duration) if duration is not None else None,
        "bitrate": int(bitrate) if bitrate is not None else None,
    }
