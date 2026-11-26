from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select, text

from smishing_backend.config import Settings
from smishing_backend.data.repositories.poisoning import flag_content
from smishing_backend.data.schema import labels
from smishing_backend.main import create_app
from smishing_backend.review_auth import AdminSettings, ReviewSettings

PATH = "/api/v1/admin/contributions"
ADMIN = {"Authorization": "Bearer synthetic-operator"}
MOBILE = {"X-API-Key": "synthetic-mobile"}
REVIEWER = {"Authorization": "Bearer synthetic-reviewer"}
DECISION = {"decision": "accepted", "reason": "quality_checked", "label": "smishing"}


def app_for(pg, *, enabled=True, failed_limit=20, behind_tls_proxy=False):
    return create_app(
        Settings(api_key=SecretStr("synthetic-mobile"), rate_limit_per_minute=8, behind_tls_proxy=behind_tls_proxy),
        admin_settings=AdminSettings(
            credentials={"operator": SecretStr("synthetic-operator")} if enabled else {},
            failed_requests_per_minute=failed_limit,
        ),
        review_settings=ReviewSettings(credentials={"reviewer": SecretStr("synthetic-reviewer")}),
        management_engine=pg,
    )


@pytest.fixture
def client(pg):
    with TestClient(app_for(pg), base_url="https://testserver") as client:
        yield client


def contribute(client, text="Aporte sintético para revisar <URL>", label="safe"):
    response = client.post("/api/v1/contributions", headers=MOBILE, json={"text": text, "label": label, "model_version": "1.0.0"})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_authentication_before_body_and_isolated_failed_quota(pg):
    with TestClient(app_for(pg, failed_limit=3), base_url="https://testserver") as client:
        for headers in ({}, MOBILE, REVIEWER):
            response = client.patch(PATH + "/invalid/review", headers=headers, content=b"not json")
            assert response.status_code == 401
            assert response.headers["cache-control"] == "no-store"
        throttled = client.get(PATH)
        assert throttled.status_code == 429 and int(throttled.headers["retry-after"]) >= 1
        assert client.get(PATH, headers=ADMIN).status_code == 200
        contribute(client)
    with TestClient(app_for(pg, enabled=False), base_url="https://testserver") as client:
        assert client.get(PATH, headers=ADMIN).status_code == 401


@pytest.mark.parametrize("collision", ["synthetic-mobile", "synthetic-reviewer"])
def test_refuse_reused_admin_credentials(collision):
    with pytest.raises(RuntimeError):
        create_app(
            Settings(api_key=SecretStr("synthetic-mobile")),
            admin_settings=AdminSettings(credentials={"operator": SecretStr(collision)}),
            review_settings=ReviewSettings(credentials={"reviewer": SecretStr("synthetic-reviewer")}),
        )


def test_tls_and_swagger_contract(pg):
    with TestClient(app_for(pg, behind_tls_proxy=True)) as client:
        assert client.get(PATH, headers=ADMIN).status_code == 400
        res = client.get(PATH, headers={**ADMIN, "X-Forwarded-Proto": "https"})
        assert res.status_code == 200
        assert res.headers["cache-control"] == "no-store"
        schema = client.get("/openapi.json").json()
        assert schema["paths"][PATH]["get"]["security"] == [{"AdministrativeBearer": []}]
        assert set(schema["paths"]["/api/v1/contributions"]) == {"post"}
        assert client.get("/docs").status_code == 200


def test_filters_pagination_terminal_review_and_single_delete(client, pg):
    before = datetime.now(UTC).isoformat()
    first = contribute(client)
    second = contribute(client, "Otro aporte sintético <PHONE>")
    with pg.begin() as connection:
        flag_content(connection, UUID(first), "evaluation_similarity")
        connection.execute(text("UPDATE contributed_message SET received_at = now()"))
    denied = client.patch(f"{PATH}/{first}/review", headers=ADMIN, json=DECISION)
    assert denied.status_code == 409
    assert client.patch(f"{PATH}/{first}/review", headers=ADMIN, json={**DECISION, "reviewer_id": "private-echo-marker"}).status_code == 422
    accepted = client.patch(f"{PATH}/{first}/review", headers=ADMIN, json={**DECISION, "acknowledge_flags": True})
    assert accepted.status_code == 200
    assert accepted.headers["cache-control"] == "no-store"
    assert accepted.json()["reviewer_id"] == "operator"
    assert client.patch(f"{PATH}/{first}/review", headers=ADMIN, json=DECISION).status_code == 409
    rejected = client.patch(f"{PATH}/{second}/review", headers=ADMIN, json={**DECISION, "decision": "rejected", "label": "safe", "reason": "invalid_content"})
    assert rejected.status_code == 200
    with pg.begin() as connection:
        flag_content(connection, UUID(second), "label_conflict")

    combined = dict(status="accepted", received_from=before, received_to=datetime.now(UTC).isoformat(),
        reviewed_from=before, reviewed_to=datetime.now(UTC).isoformat(), category="smishing",
        source="manual", model_version="1.0.0", reason="quality_checked", has_risk="false")
    result = client.get(PATH, params=combined, headers=ADMIN)
    assert result.status_code == 200, result.text
    assert result.headers["cache-control"] == "no-store"
    assert [(x["id"], x["model_version"], x["automatic_label"]) for x in result.json()] == [(first, "1.0.0", "safe")]
    for params in [
        {"status": "accepted"}, {"category": "smishing"}, {"reason": "quality_checked"},
        {"source": "manual", "status": "accepted"}, {"has_risk": "false"}, {"has_risk": "true"},
        {"model_version": "1.0.0"}, {"received_from": before}, {"reviewed_from": before},
        {"received_to": before}, {"reviewed_to": before},
    ]:
        filtered = client.get(PATH, params=params, headers=ADMIN)
        assert filtered.status_code == 200
        expect = {second} if params == {"has_risk": "true"} else ({first, second} if next(iter(params)) in {"model_version", "received_from", "reviewed_from"} else (set() if any(k.endswith("_to") for k in params) else {first}))
        assert {row["id"] for row in filtered.json()} == expect
    for order, reverse in [("asc", False), ("desc", True)]:
        for offset, expected in enumerate(sorted([first, second], reverse=reverse)):
            response = client.get(PATH, params={"order": order, "limit": 1, "offset": offset}, headers=ADMIN)
            assert [row["id"] for row in response.json()] == [expected]
    bad = client.get(PATH, params={"text": "private-echo-marker"}, headers=ADMIN)
    assert bad.status_code == 422 and "private-echo-marker" not in bad.text
    assert client.get(PATH, params={"received_from": "2026-01-01"}, headers=ADMIN).status_code == 422
    assert client.get(PATH, params={"status": "pending"}, headers=ADMIN).json() == []
    with pg.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(labels)) == 4
    assert client.delete(PATH, headers=ADMIN).status_code == 405
    removed = client.delete(f"{PATH}/{first}", headers=ADMIN)
    assert removed.status_code == 204 and removed.headers["cache-control"] == "no-store"
    assert client.delete(f"{PATH}/{first}", headers=ADMIN).status_code == 404
    assert [row["id"] for row in client.get(PATH, headers=ADMIN).json()] == [second]


def test_database_failure_rolls_back_review(client, pg):
    identity = contribute(client)
    with pg.begin() as connection:
        connection.execute(text("ALTER TABLE reviews ADD CONSTRAINT synthetic_test CHECK (false)"))
    failed = client.patch(f"{PATH}/{identity}/review", headers=ADMIN, json=DECISION)
    assert failed.status_code == 503 and "synthetic_test" not in failed.text
    rows = client.get(PATH, headers=ADMIN).json()
    assert len(rows) == 1 and rows[0]["status"] == "pending" and rows[0]["source"] == "device"
