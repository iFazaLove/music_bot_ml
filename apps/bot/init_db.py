from core.db import models  # noqa: F401  -- важно, чтобы модели были импортированы
from core.db.base import Base, engine


def init_db() -> None:
    Base.metadata.create_all(engine)
