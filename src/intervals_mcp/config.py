"""Environment-based configuration."""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or a local .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        extra="ignore",
        populate_by_name=True,
    )

    intervals_api_key: SecretStr = Field(validation_alias="INTERVALS_API_KEY")
    intervals_athlete_id: str = Field(default="0", validation_alias="INTERVALS_ATHLETE_ID")
    intervals_base_url: str = Field(
        default="https://intervals.icu/api/v1", validation_alias="INTERVALS_BASE_URL"
    )
    draft_prefix: str = Field(default="[IA]", validation_alias="INTERVALS_DRAFT_PREFIX")
    managed_marker: str = Field(
        default="[intervals-mcp:managed]", validation_alias="INTERVALS_MANAGED_MARKER"
    )
    personal_context_file: str = Field(
        default="PERSONAL.md", validation_alias="INTERVALS_PERSONAL_CONTEXT_FILE"
    )
    request_timeout_seconds: float = Field(
        default=20.0,
        gt=0,
        le=120,
        validation_alias="INTERVALS_REQUEST_TIMEOUT_SECONDS",
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached runtime settings."""

    return Settings()  # type: ignore[call-arg]
