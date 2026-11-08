"""Runtime configuration supplied by the process environment."""

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SMISHING_", extra="ignore")

    database_url: str = "postgresql+psycopg://localhost/smishing"
    rate_limit_per_minute: int = Field(default=60, ge=1)
    api_key: SecretStr | None = None
    api_keys: list[SecretStr] = Field(default_factory=list)
