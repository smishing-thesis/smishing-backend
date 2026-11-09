import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select

from smishing_backend.config import Settings
from smishing_backend.data.repositories.contributions import (
    PostgresContributionRepository,
)
from smishing_backend.data.schema import contributions
from smishing_backend.domain.privacy import (
    MODEL_VERSION,
    RULES_VERSION,
    ResidualPersonalData,
    assert_anonymized,
    load_name_detector,
)
from smishing_backend.main import create_app

# Invented data only. Domains under .invalid are reserved for examples.
SYNTHETIC_RESIDUALS = [
    "Visita https://example.invalid/prueba",
    "Visita example.invalid/prueba",
    "Escribe a persona@example.invalid",
    "Llama al 900000001",
    "DNI 00000001 pendiente",
    "RUC 10000000001 pendiente",
    "Estimado Juan Pérez, su solicitud está lista.",
]


def test_real_versioned_ner():
    assert RULES_VERSION == "1.3.0"
    assert load_name_detector().meta["version"] == MODEL_VERSION


@pytest.mark.parametrize("text", SYNTHETIC_RESIDUALS)
def test_residuals_rejected(text):
    with pytest.raises(ResidualPersonalData):
        assert_anonymized(text)


@pytest.mark.parametrize(
    "text",
    [
        "Mensaje de prueba",
        "Visita <URL>",
        "Estimado <NAMED_ENTITY> llama <PHONE_NUMBER>",
        "DNI <ID_NUMBER> correo <EMAIL_ADDRESS>",
    ],
)
def test_anonymized_accepted(text):
    assert_anonymized(text)


@pytest.mark.parametrize("text", SYNTHETIC_RESIDUALS)
def test_no_persistence_or_logs(pg, caplog, text):
    app = create_app(
        Settings(api_key=SecretStr("synthetic")), PostgresContributionRepository(pg)
    )
    with TestClient(app, base_url="https://testserver") as client:
        response = client.post(
            "/api/v1/contributions",
            headers={"X-API-Key": "synthetic"},
            json={"text": text, "label": "safe", "model_version": "1.0.0"},
        )
        assert response.status_code == 422
        assert text not in response.text
    assert text not in caplog.text
    with pg.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(contributions)) == 0


def test_detector_failure_never_stores(pg, monkeypatch):
    from smishing_backend.domain import privacy

    app = create_app(
        Settings(api_key=SecretStr("synthetic")), PostgresContributionRepository(pg)
    )
    with TestClient(app, base_url="https://testserver") as client:

        def unavailable():
            raise RuntimeError("synthetic detector failure")

        monkeypatch.setattr(privacy, "load_name_detector", unavailable)
        response = client.post(
            "/api/v1/contributions",
            headers={"X-API-Key": "synthetic"},
            json={
                "text": "Mensaje sintético",
                "label": "safe",
                "model_version": "1.0.0",
            },
        )
        assert response.status_code == 503
        assert "synthetic detector failure" not in response.text
    with pg.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(contributions)) == 0
