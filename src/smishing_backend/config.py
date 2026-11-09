"""Runtime configuration supplied by the process environment."""

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SMISHING_", extra="ignore")

    database_url: str = "postgresql+psycopg://localhost/smishing"
    rate_limit_per_minute: int = Field(default=60, ge=1)
    api_key: SecretStr | None = None
    api_keys: list[SecretStr] = Field(default_factory=list)
    global_rate_limit_per_minute: int = Field(default=600, ge=1)
    poison_window_seconds: int = Field(default=300, ge=1, le=3600)
    poison_history_limit: int = Field(default=500, ge=30, le=2000)
    poison_similarity_threshold: float = Field(default=0.9, ge=0.5, le=1)
    poison_similar_count: int = Field(default=5, ge=2, le=100)
    poison_min_text_length: int = Field(default=30, ge=3, le=2048)
    poison_min_baseline: int = Field(default=20, ge=2, le=1000)
    poison_min_recent: int = Field(default=10, ge=2, le=1000)
    poison_class_delta: float = Field(default=0.4, gt=0, le=1)
    poison_evaluation_threshold: float = Field(default=0.9, ge=0.5, le=1)
    poison_evaluation_fingerprints_path: Path | None = None
