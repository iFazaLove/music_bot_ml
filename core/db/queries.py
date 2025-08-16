from __future__ import annotations

from typing import Tuple

from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from core.db.models import Track


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
