from __future__ import annotations

from typing import Iterable, Optional, Tuple

from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from core.db.models import Like, Track, User


def get_user_by_tg_id(s: Session, tg_id: int) -> Optional[User]:
    return s.execute(select(User).where(User.tg_id == tg_id)).scalar_one_or_none()


def get_or_create_user(s: Session, tg_id: int, username: Optional[str]) -> User:
    user = get_user_by_tg_id(s, tg_id)
    if user is None:
        user = User(tg_id=tg_id, username=username)
        s.add(user)
        s.commit()
        s.refresh(user)
    return user


def is_track_liked_by_user(s: Session, user_id: int, track_id: int) -> bool:
    return (
        s.execute(
            select(Like).where(Like.user_id == user_id, Like.track_id == track_id)
        ).scalar_one_or_none()
        is not None
    )


def get_user_track_by_id(s: Session, user_id: int, track_id: int) -> Optional[Track]:
    return s.execute(
        select(Track).where(Track.id == track_id, Track.uploader_user_id == user_id)
    ).scalar_one_or_none()


def _fetch_with_has_more(
    s: Session, stmt: Select[Tuple[Track]], limit: int
) -> Tuple[list[Track], bool]:
    """Выполнить stmt, получить limit+1 записей, вернуть первые limit и флаг has_more."""
    rows = s.execute(stmt.limit(limit + 1)).scalars().all()
    has_more = len(rows) > limit
    return list(rows[:limit]), has_more


def fetch_user_tracks(
    s: Session, user_id: int, offset: int, limit: int
) -> Tuple[list[Track], bool]:
    """Все треки пользователя, пагинация."""
    stmt = (
        select(Track)
        .where(Track.uploader_user_id == user_id)
        .order_by(Track.id.desc())
        .offset(offset)
    )
    return _fetch_with_has_more(s, stmt, limit)


def get_track_by_storage_path(s: Session, storage_path: str) -> Optional[Track]:
    return s.execute(select(Track).where(Track.storage_path == storage_path)).scalar_one_or_none()


def get_liked_track_ids(s: Session, user_id: int, track_ids: Iterable[int]) -> set[int]:
    ids = list(track_ids)
    if not ids:
        return set()
    rows = s.execute(
        select(Like.track_id).where(Like.user_id == user_id, Like.track_id.in_(ids))
    ).scalars()
    return set(rows.all())


def fetch_user_tracks_by_query(
    s: Session, user_id: int, query: str, offset: int, limit: int
) -> Tuple[list[Track], bool]:
    """Треки пользователя по поиску в title/artist, пагинация."""
    like = f"%{query}%"
    stmt = (
        select(Track)
        .where(
            Track.uploader_user_id == user_id,
            or_(Track.title.like(like), Track.artist.like(like)),
        )
        .order_by(Track.id.desc())
        .offset(offset)
    )
    return _fetch_with_has_more(s, stmt, limit)


def fetch_user_liked_tracks(
    s: Session, user_id: int, offset: int, limit: int
) -> Tuple[list[Track], bool]:
    """Только лайкнутые пользователем треки; сортировка по времени лайка (сначала новые)."""
    stmt: Select[tuple[Track]] = (
        select(Track)
        .join(Like, Like.track_id == Track.id)
        .where(Like.user_id == user_id)
        .order_by(Like.created_at.desc(), Track.id.desc())
        .offset(offset)
    )
    return _fetch_with_has_more(s, stmt, limit)


def fetch_user_liked_tracks_by_query(
    s: Session,
    user_id: int,
    query: str,
    offset: int,
    limit: int,
) -> tuple[list[Track], bool]:
    """Лайкнутые + фильтр по title/artist."""
    like = f"%{query}%"
    stmt: Select[tuple[Track]] = (
        select(Track)
        .join(Like, Like.track_id == Track.id)
        .where(
            Like.user_id == user_id,
            or_(Track.title.like(like), Track.artist.like(like)),
        )
        .order_by(Like.created_at.desc(), Track.id.desc())
        .offset(offset)
    )
    return _fetch_with_has_more(s, stmt, limit)


def search_tracks_global(
    s: Session,
    q: Optional[str],
    artist: Optional[str],
    title: Optional[str],
    offset: int,
    limit: int,
    sort: str = "recent",
) -> Tuple[list[Track], bool]:
    conditions = []
    if artist:
        conditions.append(Track.artist.like(f"%{artist}%"))
    if title:
        conditions.append(Track.title.like(f"%{title}%"))
    if q:
        like = f"%{q}%"
        conditions.append(or_(Track.title.like(like), Track.artist.like(like)))

    stmt: Select[tuple[Track]] = select(Track)
    if conditions:
        stmt = stmt.where(*conditions)

    if sort == "popular":
        stmt = stmt.order_by(Track.likes_count.desc(), Track.id.desc())
    else:
        stmt = stmt.order_by(Track.id.desc())

    stmt = stmt.offset(offset)
    return _fetch_with_has_more(s, stmt, limit)
