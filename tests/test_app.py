import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from smishing_backend.config import Settings
from smishing_backend.main import create_app


def test_health_endpoint() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_configuration_comes_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMISHING_DATABASE_URL", "sqlite:///./data/test.db")
    monkeypatch.setenv("SMISHING_RATE_LIMIT_PER_MINUTE", "7")
    monkeypatch.setenv("SMISHING_API_KEY", "synthetic-test-key")

    settings = Settings()

    assert settings.database_url == "sqlite:///./data/test.db"
    assert settings.rate_limit_per_minute == 7
    assert settings.api_key is not None
    assert settings.api_key.get_secret_value() == "synthetic-test-key"
    assert "synthetic-test-key" not in repr(settings)


def test_rate_limit_must_be_positive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMISHING_RATE_LIMIT_PER_MINUTE", "0")

    with pytest.raises(ValidationError):
        Settings()
