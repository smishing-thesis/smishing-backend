"""Batch endpoint against real PostgreSQL; synthetic messages only."""

import logging

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from smishing_backend.api.contracts import MAX_BATCH_ITEMS, contract_app
from smishing_backend.config import Settings
from smishing_backend.data.repositories.contributions import (
    PostgresContributionRepository,
)
from smishing_backend.data.schema import contributions, labels
from smishing_backend.main import create_app

URL = "/api/v1/contributions/batch"
HEADERS = {"X-API-Key": "synthetic"}


def item(text, label="smishing", model_version="1.0.0"):
    return {"text": text, "label": label, "model_version": model_version}


@pytest.fixture
def application(pg):
    return create_app(
        Settings(api_key=SecretStr("synthetic")), PostgresContributionRepository(pg)
    )


def count(pg, table=contributions):
    with pg.connect() as conn:
        return conn.scalar(select(func.count()).select_from(table))


def test_runtime_schema_matches_contract(application):
    schema = application.openapi()
    proposal = contract_app().openapi()
    assert schema["paths"][URL] == proposal["paths"][URL]
    for name, value in proposal["components"]["schemas"].items():
        assert schema["components"]["schemas"][name] == value
    assert set(proposal["paths"][URL]["post"]["responses"]) == {
        "200",
        "400",
        "401",
        "413",
        "422",
        "429",
        "503",
    }
    body = proposal["components"]["schemas"]["ContributionBatchInput"]
    assert body["properties"]["contributions"]["maxItems"] == MAX_BATCH_ITEMS
    assert body["additionalProperties"] is False


def test_mixed_batch_returns_one_result_per_contribution(application, pg, caplog):
    texts = {
        "ok": "Aporte sintético uno <URL>",
        "residual": "Llama al 900000001",
        "other": "Aporte sintético dos <PHONE_NUMBER>",
    }
    batch = {
        "contributions": [
            item(texts["ok"]),
            item(texts["residual"]),
            item(texts["ok"]),  # same content inside the batch
            item(texts["other"], "safe", "9.9.9"),  # version without a publication
            item("", "smishing"),  # breaks the contract
            item(texts["other"], "safe"),
        ]
    }
    caplog.set_level(logging.DEBUG)
    with TestClient(application, base_url="https://testserver") as client:
        response = client.post(URL, headers=HEADERS, json=batch)
        assert response.status_code == 200
        assert response.json() == {
            "results": [
                {"index": 0, "status": "accepted"},
                {"index": 1, "status": "rejected", "reason": "not_anonymized"},
                {"index": 2, "status": "duplicate"},
                {"index": 3, "status": "rejected", "reason": "unknown_model_version"},
                {"index": 4, "status": "rejected", "reason": "invalid_contribution"},
                {"index": 5, "status": "accepted"},
            ]
        }
        for text in texts.values():
            assert text not in response.text
            assert text not in caplog.text
        assert "900000001" not in response.text + caplog.text
        # Resending is idempotent: everything stored comes back as a duplicate.
        again = client.post(URL, headers=HEADERS, json=batch).json()["results"]
        # Index 3 is now a duplicate too: existing content is checked before the
        # version, exactly as the single endpoint answers 409 before 422.
        assert [r["status"] for r in again] == [
            "duplicate",
            "rejected",
            "duplicate",
            "duplicate",
            "rejected",
            "duplicate",
        ]
    assert count(pg) == 2
    assert count(pg, labels) == 2


def test_one_bad_contribution_does_not_affect_the_rest(application, pg):
    batch = {
        "contributions": [item("Llama al 900000001")]
        + [item(f"Sintético {i} <URL>") for i in range(5)]
    }
    with TestClient(application, base_url="https://testserver") as client:
        results = client.post(URL, headers=HEADERS, json=batch).json()["results"]
    assert results[0]["status"] == "rejected"
    assert [r["status"] for r in results[1:]] == ["accepted"] * 5
    assert count(pg) == 5


def test_authentication_and_transport(application, pg):
    batch = {"contributions": [item("Sintético <URL>")]}
    with TestClient(application, base_url="https://testserver") as client:
        assert client.post(URL, json=batch).status_code == 401
        wrong = client.post(URL, headers={"X-API-Key": "wrong"}, json=batch)
        assert wrong.status_code == 401
    with TestClient(application) as client:  # plain HTTP never stores
        assert client.post(URL, headers=HEADERS, json=batch).status_code == 400
    assert count(pg) == 0


def test_quota_counts_each_contribution(pg):
    application = create_app(
        Settings(api_key=SecretStr("synthetic"), rate_limit_per_minute=25),
        PostgresContributionRepository(pg),
    )
    batch = {"contributions": [item(f"Sintético {i} <URL>") for i in range(20)]}
    with TestClient(application, base_url="https://testserver") as client:
        assert client.post(URL, headers=HEADERS, json=batch).status_code == 200
        refused = client.post(
            URL,
            headers=HEADERS,
            json={"contributions": [item(f"Otro {i} <URL>") for i in range(6)]},
        )
        assert refused.status_code == 429
        assert int(refused.headers["Retry-After"]) > 0
    assert count(pg) == 20


def test_storage_failure_is_a_generic_503(application, monkeypatch):
    def broken(self, contribution):
        raise OperationalError("secret statement", {"text": "x"}, Exception("down"))

    monkeypatch.setattr(PostgresContributionRepository, "save", broken)
    with TestClient(application, base_url="https://testserver") as client:
        response = client.post(
            URL, headers=HEADERS, json={"contributions": [item("Sintético <URL>")]}
        )
    assert response.status_code == 503
    assert response.json() == {
        "error": {"code": "service_unavailable", "message": "Servicio no disponible."}
    }
    assert "secret" not in response.text
