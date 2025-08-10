from typing import TYPE_CHECKING

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="APP_")
    tg_token: str  # APP_TG_TOKEN=...
    db_dsn: str = "sqlite:///./music.db"  # позже поменяем на Postgres


if TYPE_CHECKING:
    settings: Settings
else:
    settings = Settings()
