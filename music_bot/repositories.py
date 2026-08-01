from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from music_bot.models import LibraryEntry, Track, TrackLike, User


@dataclass(frozen=True, slots=True)
class TrackInput:
    telegram_file_id: str
    telegram_file_unique_id: str
    content_hash: str
    title: str
    artist: str
    album: str | None
    duration: float | None
    file_size: int | None


def get_user_by_telegram_id(session: Session, telegram_id: int) -> User | None:
    return session.scalar(select(User).where(User.telegram_id == telegram_id))


def get_or_create_user(session: Session, telegram_id: int, username: str | None) -> User:
    user = get_user_by_telegram_id(session, telegram_id)
    if user is None:
        user = User(telegram_id=telegram_id, username=username)
        session.add(user)
        session.flush()
    elif user.username != username:
        user.username = username
    return user


def get_track_by_unique_id(session: Session, file_unique_id: str) -> Track | None:
    return session.scalar(select(Track).where(Track.telegram_file_unique_id == file_unique_id))


def get_track_by_content_hash(session: Session, content_hash: str) -> Track | None:
    return session.scalar(select(Track).where(Track.content_hash == content_hash))


def get_track_by_id(session: Session, track_id: int) -> Track | None:
    return session.get(Track, track_id)


def add_track_to_library(session: Session, user: User, track: Track) -> bool:
    entry = session.get(LibraryEntry, (user.id, track.id))
    if entry is not None:
        return False

    session.add(LibraryEntry(user_id=user.id, track_id=track.id))
    session.flush()
    return True


def get_user_library(session: Session, user: User, limit: int = 10) -> list[Track]:
    statement = (
        select(Track)
        .join(LibraryEntry, LibraryEntry.track_id == Track.id)
        .where(LibraryEntry.user_id == user.id)
        .order_by(LibraryEntry.added_at.desc())
        .limit(limit)
    )
    return list(session.scalars(statement))


def get_library_track_ids(session: Session, user: User, tracks: list[Track]) -> set[int]:
    track_ids = [track.id for track in tracks]
    if not track_ids:
        return set()

    statement = select(LibraryEntry.track_id).where(
        LibraryEntry.user_id == user.id,
        LibraryEntry.track_id.in_(track_ids),
    )
    return set(session.scalars(statement))


def search_tracks(session: Session, query: str, limit: int = 10) -> list[Track]:
    pattern = f"%{query.strip()}%"
    statement = (
        select(Track)
        .where(or_(Track.title.ilike(pattern), Track.artist.ilike(pattern)))
        .order_by(Track.artist, Track.title)
        .limit(limit)
    )
    return list(session.scalars(statement))


def get_liked_track_ids(session: Session, user: User, tracks: list[Track]) -> set[int]:
    track_ids = [track.id for track in tracks]
    if not track_ids:
        return set()

    statement = select(TrackLike.track_id).where(
        TrackLike.user_id == user.id,
        TrackLike.track_id.in_(track_ids),
    )
    return set(session.scalars(statement))


def get_liked_tracks(session: Session, user: User) -> list[Track]:
    statement = (
        select(Track)
        .join(TrackLike, TrackLike.track_id == Track.id)
        .where(TrackLike.user_id == user.id)
    )
    return list(session.scalars(statement))


def get_all_tracks(session: Session) -> list[Track]:
    return list(session.scalars(select(Track)))


def get_track_like_counts(session: Session, tracks: list[Track]) -> dict[int, int]:
    track_ids = [track.id for track in tracks]
    if not track_ids:
        return {}

    statement = (
        select(TrackLike.track_id, func.count())
        .where(TrackLike.track_id.in_(track_ids))
        .group_by(TrackLike.track_id)
    )
    return {track_id: count for track_id, count in session.execute(statement)}


def toggle_track_like(session: Session, user: User, track: Track) -> bool:
    like = session.get(TrackLike, (user.id, track.id))
    if like is not None:
        session.delete(like)
        session.flush()
        return False

    session.add(TrackLike(user_id=user.id, track_id=track.id))
    session.flush()
    return True


def save_track(session: Session, uploader: User, data: TrackInput) -> tuple[Track, bool]:
    existing = get_track_by_content_hash(session, data.content_hash)
    if existing is None:
        existing = get_track_by_unique_id(session, data.telegram_file_unique_id)

    if existing is not None:
        existing.telegram_file_id = data.telegram_file_id
        existing.telegram_file_unique_id = data.telegram_file_unique_id
        existing.content_hash = data.content_hash
        return existing, False

    track = Track(
        telegram_file_id=data.telegram_file_id,
        telegram_file_unique_id=data.telegram_file_unique_id,
        content_hash=data.content_hash,
        title=data.title,
        artist=data.artist,
        album=data.album,
        duration=data.duration,
        file_size=data.file_size,
        uploader_user_id=uploader.id,
    )
    session.add(track)
    session.flush()
    return track, True
