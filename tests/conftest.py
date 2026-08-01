from collections.abc import Generator

import pytest
from sqlalchemy import Engine

from music_bot.database import SessionFactory, create_database, init_database


@pytest.fixture
def database(tmp_path) -> Generator[tuple[Engine, SessionFactory], None, None]:
    engine, session_factory = create_database(f"sqlite:///{tmp_path / 'test.db'}")
    init_database(engine)
    yield engine, session_factory
    engine.dispose()
