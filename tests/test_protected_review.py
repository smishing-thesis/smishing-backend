from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, insert, select, text
from sqlalchemy.exc import IntegrityError

from smishing_backend.config import Settings
from smishing_backend.data.repositories.contributions import (
    PostgresContributionRepository,
)
from smishing_backend.data.repositories.review import PostgresReviewRepository
from smishing_backend.data.schema import contributions, labels, reviews
from smishing_backend.domain.contributions import Label, NewContribution
from smishing_backend.main import create_app
from smishing_backend.review import create_review_app
from smishing_backend.review_auth import ReviewSettings

AUTH = {"Authorization": "Bearer synthetic-review-token"}
DECISION = {"decision": "accepted", "reason": "quality_checked", "label": "safe"}


@pytest.fixture
def review_system(pg):
    repository = PostgresContributionRepository(pg)
    item = repository.save(
        NewContribution(
            "Mensaje sintético <URL>", "a" * 64, (Label("smishing", "1.0.0"),)
        )
    )
    app = create_review_app(
        ReviewSettings(
            credentials={"reviewer-demo": SecretStr("synthetic-review-token")}
        ),
        Settings(api_key=SecretStr("synthetic-app-token")),
        PostgresReviewRepository(pg),
    )
    with TestClient(app, base_url="https://testserver") as client:
        yield item.id, app, client


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"X-API-Key": "synthetic-app-token"},
        {"Authorization": "Bearer synthetic-app-token"},
        {"Authorization": "Bearer wrong"},
        [
            ("Authorization", "Bearer synthetic-review-token"),
            ("Authorization", "Bearer wrong"),
        ],
    ],
)
def test_app_or_missing_credential_cannot_list_or_review(review_system, pg, headers):
    cid, _, client = review_system
    assert client.get("/reviews/pending", headers=headers).status_code == 401
    assert (
        client.post(f"/reviews/{cid}", headers=headers, content=b"not json").status_code
        == 401
    )
    with pg.connect() as conn:
        assert conn.scalar(select(contributions.c.status)) == "pending"
        assert conn.scalar(select(func.count()).select_from(reviews)) == 0


@pytest.mark.parametrize("decision", ["accepted", "rejected"])
def test_reviewer_lists_decides_corrects_label_and_is_recorded(
    review_system, pg, decision
):
    cid, _, client = review_system
    pending = client.get("/reviews/pending", headers=AUTH)
    assert pending.status_code == 200 and [row["id"] for row in pending.json()] == [
        str(cid)
    ]
    response = client.post(
        f"/reviews/{cid}", headers=AUTH, json={**DECISION, "decision": decision}
    )
    assert response.status_code == 201
    assert response.json()["reviewer_id"] == "reviewer-demo"
    assert response.json()["label"] == "safe"
    assert response.json()["reviewed_at"]
    assert client.get("/reviews/pending", headers=AUTH).json() == []
    assert (
        client.post(f"/reviews/{cid}", headers=AUTH, json=DECISION).status_code == 409
    )
    with pg.connect() as conn:
        row = conn.execute(select(reviews)).one()
        assert row.reviewer_id == "reviewer-demo" and row.decision == decision
        assert row.reviewed_at == conn.scalar(select(contributions.c.reviewed_at))
        manual = conn.execute(select(labels).where(labels.c.id == row.label_id)).one()
        assert (
            manual.origin == "manual"
            and manual.model_version_id is None
            and manual.value == "safe"
        )
        assert conn.scalar(select(func.count()).select_from(labels)) == 2


def test_public_contract_and_app_do_not_expose_reviews(pg):
    app = create_app(Settings(), PostgresContributionRepository(pg))
    assert not any(path.startswith("/reviews") for path in app.openapi()["paths"])
    with TestClient(app, base_url="https://testserver") as client:
        assert client.get("/reviews/pending", headers=AUTH).status_code == 404


def test_cannot_spoof_reviewer_or_echo_values(review_system, pg):
    cid, _, client = review_system
    response = client.post(
        f"/reviews/{cid}",
        headers=AUTH,
        json={
            **DECISION,
            "reviewer_id": "forged-reviewer",
            "text": "SYNTHETIC_PRIVATE_TEXT",
        },
    )
    assert response.status_code == 422
    assert (
        "forged-reviewer" not in response.text
        and "SYNTHETIC_PRIVATE_TEXT" not in response.text
    )
    with pg.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(reviews)) == 0


def test_body_limit_and_https(review_system):
    cid, _, client = review_system
    assert (
        client.post(f"/reviews/{cid}", headers=AUTH, content=b" " * 2049).status_code
        == 413
    )
    assert (
        client.get("http://testserver/reviews/pending", headers=AUTH).status_code == 400
    )


def test_review_storage_failure_rolls_back_status_label_and_audit(review_system, pg):
    cid, _, client = review_system
    with pg.begin() as conn:
        conn.execute(
            text(
                "CREATE FUNCTION reject_synthetic_audit() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'synthetic failure'; END; $$ LANGUAGE plpgsql"
            )
        )
        conn.execute(
            text(
                "CREATE TRIGGER reject_synthetic_audit BEFORE INSERT ON reviews FOR EACH ROW EXECUTE FUNCTION reject_synthetic_audit()"
            )
        )
    response = client.post(f"/reviews/{cid}", headers=AUTH, json=DECISION)
    assert response.status_code == 503 and "synthetic failure" not in response.text
    with pg.connect() as conn:
        assert conn.scalar(select(contributions.c.status)) == "pending"
        assert conn.scalar(select(func.count()).select_from(labels)) == 1
        assert conn.scalar(select(func.count()).select_from(reviews)) == 0


def test_concurrent_reviews_only_one_wins(review_system, pg):
    cid, _, client = review_system

    def send(decision):
        return client.post(
            f"/reviews/{cid}", headers=AUTH, json={**DECISION, "decision": decision}
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(send, ["accepted", "rejected"])) == [201, 409]
    with pg.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(reviews)) == 1
        assert conn.scalar(select(func.count()).select_from(labels)) == 2


def test_reviewer_credentials_must_not_reuse_app_key():
    with pytest.raises(RuntimeError, match="separate from app"):
        create_review_app(
            ReviewSettings(
                credentials={"reviewer-demo": SecretStr("same-synthetic-key")}
            ),
            Settings(api_key=SecretStr("same-synthetic-key")),
        )


def test_empty_reviewer_configuration_fails_closed():
    app = create_review_app(ReviewSettings(credentials={}), Settings())
    with TestClient(app, base_url="https://testserver") as client:
        assert client.get("/reviews/pending", headers=AUTH).status_code == 401


def test_database_audit_cannot_reference_device_label(review_system, pg):
    cid, _, _ = review_system
    with pg.connect() as conn:
        label_id = conn.scalar(select(labels.c.id))
    with pytest.raises(IntegrityError), pg.begin() as conn:
        conn.execute(
            insert(reviews).values(
                id=uuid4(),
                contribution_id=cid,
                label_id=label_id,
                reviewer_id="reviewer-demo",
                decision="accepted",
                reason="quality_checked",
                reviewed_at=func.now(),
            )
        )
