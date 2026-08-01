from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


type SessionFactory = sessionmaker[Session]


def create_database(database_url: str) -> tuple[Engine, SessionFactory]:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, connect_args=connect_args)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return engine, factory


def init_database(engine: Engine) -> None:
    from music_bot.models import LibraryEntry, Track

    Base.metadata.create_all(engine)

    # Треки из версии без личных библиотек принадлежат их первым загрузчикам.
    with Session(engine) as session:
        tracks = session.scalars(select(Track)).all()
        for track in tracks:
            entry_key = (track.uploader_user_id, track.id)
            if session.get(LibraryEntry, entry_key) is None:
                session.add(
                    LibraryEntry(
                        user_id=track.uploader_user_id,
                        track_id=track.id,
                    )
                )
        session.commit()


@contextmanager
def session_scope(factory: SessionFactory) -> Generator[Session, None, None]:
    with factory() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
