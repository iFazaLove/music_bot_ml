from datetime import datetime, timezone

from sqlalchemy import BigInteger, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from core.db.base import Base


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(default=now_utc)


class Track(Base):
    __tablename__ = "tracks"
    __table_args__ = (
        Index("idx_tracks_title", "title"),
        Index("idx_tracks_artist", "artist"),
        Index("idx_tracks_likes_count", "likes_count"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    storage_path: Mapped[str] = mapped_column(String(1024), unique=True, index=True)
    title: Mapped[str | None] = mapped_column(String(512))
    artist: Mapped[str | None] = mapped_column(String(512))
    album: Mapped[str | None] = mapped_column(String(512))
    duration: Mapped[float | None] = mapped_column(Float)
    bitrate: Mapped[int | None] = mapped_column(Integer)
    size: Mapped[int | None] = mapped_column(BigInteger)
    uploader_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    likes_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Like(Base):
    __tablename__ = "likes"

    # Составной первичный ключ
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id"), primary_key=True)

    created_at: Mapped[datetime] = mapped_column(default=now_utc)

    source: Mapped[str] = mapped_column(String(16), default="manual", nullable=False)
