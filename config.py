from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Bitbucket Server
    BITBUCKET_SERVER_URL: str
    BITBUCKET_SERVER_PORT: int
    BITBUCKET_SERVER_USERNAME: str
    BITBUCKET_SERVER_PASSWORD: str

    ATLASSIAN_EMAIL: str

    # Bitbucket Cloud
    CLOUD_WORKSPACE: str
    BITBUCKET_SSH_KEY: Path = Path("~/.ssh/bitbucket_migracao")
    BITBUCKET_CLOUD_API_URL: str
    BITBUCKET_CLOUD_TOKEN: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
