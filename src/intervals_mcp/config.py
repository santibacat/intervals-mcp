"""Environment-based configuration."""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or a local .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="INTERVALS_",
        extra="ignore",
    )

    intervals_api_key: SecretStr
    intervals_athlete_id: str = "0"
    intervals_base_url: str = "https://intervals.icu/api/v1"
    draft_prefix: str = "[IA]"
    managed_marker: str = "[intervals-mcp:managed]"
    personal_context_file: str = "PERSONAL.md"
    request_timeout_seconds: float = Field(default=20.0, gt=0, le=120)


@lru_cache
def get_settings() -> Settings:
    """Return cached runtime settings."""

    return Settings()  # type: ignore[call-arg]
