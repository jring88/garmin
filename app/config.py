from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
    )

    garmin_email: str = ""
    garmin_password: str = ""
    database_url: str = f"sqlite+aiosqlite:///{BASE_DIR / 'data' / 'garmin_health.db'}"


settings = Settings()
