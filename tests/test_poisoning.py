import hashlib
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from smishing_backend.config import Settings
from smishing_backend.data.repositories.contributions import (
    PostgresContributionRepository,
)
from smishing_backend.data.repositories.poisoning import RiskAwareContributionRepository
from smishing_backend.data.repositories.quarantine import PostgresQuarantineRepository
from smishing_backend.data.repositories.review import PostgresReviewRepository
from smishing_backend.data.risk_config import policy_from_settings
from smishing_backend.data.schema import (
    contributions,
    labels,
    model_versions,
    risk_flags,
)
from smishing_backend.domain.contributions import (
    DuplicateContribution,
    Label,
    NewContribution,
)
from smishing_backend.domain.poisoning import (
    ObservedContribution,
    PoisoningPolicy,
    assess,
    fingerprint,
)
from smishing_backend.domain.review import ReviewDecision
from smishing_backend.domain.text import content_hash
from smishing_backend.main import create_app
from smishing_backend.review import create_review_app
from smishing_backend.review_auth import ReviewSettings

REFERENCE = "Referencia sintética de evaluación de un aviso genérico con instrucciones de prueba y enlace <URL>."
AUTH = {"Authorization": "Bearer synthetic-review-token"}


def sample(body, value="smishing"):
    return NewContribution(body, content_hash(body), (Label(value, "1.0.0"),))


def codes(pg, cid=None):
    statement = select(risk_flags.c.code).where(risk_flags.c.reviewed_at.is_(None))
    if cid:
        statement = statement.where(risk_flags.c.contribution_id == cid)
    with pg.connect() as conn:
        return set(conn.scalars(statement))


def reviewer(pg):
    return create_review_app(
        ReviewSettings(
            credentials={"reviewer-demo": SecretStr("synthetic-review-token")}
        ),
        Settings(),
        PostgresReviewRepository(pg),
    )


def test_signal_math_and_no_device_inputs():
    policy = PoisoningPolicy(
        similar_count=3, evaluation_references=(fingerprint(REFERENCE),)
    )
    recent = [ObservedContribution(REFERENCE + str(i), "smishing") for i in range(2)]
    assert set(assess(REFERENCE + "2", "smishing", recent, [], policy)) == {
        "similarity_burst",
        "evaluation_similarity",
    }
    assert assess("Breve", "safe", [], [], policy) == ()


def test_reference_configuration_and_invalid_file(tmp_path):
    file = tmp_path / "fingerprints.json"
    file.write_text(
        json.dumps(
            {
                "format": "char-ngrams-v1",
                "n": 3,
                "references": [sorted(fingerprint(REFERENCE))],
            }
        )
    )
    policy = policy_from_settings(Settings(poison_evaluation_fingerprints_path=file))
    assert assess(REFERENCE, "safe", [], [], policy) == ("evaluation_similarity",)
    assert REFERENCE not in file.read_text()
    file.write_text(
        json.dumps(
            {"format": "wrong", "n": 3, "references": [["SYNTHETIC_PRIVATE_TEXT"]]}
        )
    )
    with pytest.raises(
        RuntimeError, match="Invalid evaluation fingerprint configuration"
    ) as error:
        policy_from_settings(Settings(poison_evaluation_fingerprints_path=file))
    assert "SYNTHETIC_PRIVATE_TEXT" not in str(error.value)


def test_burst_requires_explicit_review_acknowledgement(pg):
    repo = RiskAwareContributionRepository(pg, PoisoningPolicy(similar_count=3))
    items = [repo.save(sample(REFERENCE + str(i))) for i in range(3)]
    assert codes(pg, items[-1].id) == {"similarity_burst"}
    with TestClient(reviewer(pg), base_url="https://testserver") as client:
        decision = {
            "decision": "accepted",
            "reason": "quality_checked",
            "label": "safe",
        }
        assert (
            client.post(
                f"/reviews/{items[-1].id}", headers=AUTH, json=decision
            ).status_code
            == 409
        )
        flagged = client.get("/reviews/flagged", headers=AUTH)
        assert flagged.status_code == 200 and flagged.json()[0]["id"] == str(
            items[-1].id
        )
        assert (
            client.post(
                f"/reviews/{items[-1].id}",
                headers=AUTH,
                json={**decision, "acknowledge_flags": True},
            ).status_code
            == 201
        )
    assert codes(pg, items[-1].id) == set()
    with pg.connect() as conn:
        row = conn.execute(select(risk_flags)).one()
        assert (
            row.reviewer_id == "reviewer-demo"
            and row.review_decision == "accepted"
            and row.reviewed_at is not None
        )
    assert [
        r["id"] for r in PostgresQuarantineRepository(pg).accepted_for_training()
    ] == [items[-1].id]


def test_conflicting_duplicate_blocks_accepted_export_until_new_review(pg):
    repo = RiskAwareContributionRepository(pg, PoisoningPolicy())
    item = repo.save(sample(REFERENCE))
    PostgresReviewRepository(pg).decide(
        item.id, "reviewer-demo", ReviewDecision("accepted", "quality_checked", "safe")
    )
    training = PostgresQuarantineRepository(pg)
    assert len(training.accepted_for_training()) == 1
    with pytest.raises(DuplicateContribution):
        repo.save(sample(REFERENCE, "safe"))
    assert (
        codes(pg, item.id) == {"label_conflict"}
        and training.accepted_for_training() == []
    )
    with TestClient(reviewer(pg), base_url="https://testserver") as client:
        assert (
            client.get(
                "/reviews/flagged", headers={"X-API-Key": "synthetic-app"}
            ).status_code
            == 401
        )
        assert client.post(
            f"/reviews/{item.id}/flags/acknowledge",
            headers=AUTH,
            json={"confirm": True},
        ).json() == {"reviewed_flags": 1}
    assert len(training.accepted_for_training()) == 1
    with pytest.raises(DuplicateContribution):
        repo.save(sample(REFERENCE, "safe"))
    with pytest.raises(DuplicateContribution):
        repo.save(sample(REFERENCE, "safe"))
    with pg.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(contributions)) == 1
        assert conn.scalar(select(func.count()).select_from(labels)) == 2
        assert conn.scalar(select(func.count()).select_from(risk_flags)) == 2
    assert codes(pg, item.id) == {"label_conflict"}


def test_sudden_class_shift_uses_prior_window(pg):
    raw = PostgresContributionRepository(pg)
    for i in range(20):
        raw.save(
            sample(f"Control sintético de base {i}", "safe" if i % 2 else "smishing")
        )
    with pg.begin() as conn:
        conn.execute(
            text(
                "UPDATE contributions SET received_at = now() - interval '450 seconds'"
            )
        )
    for i in range(9):
        raw.save(sample(f"Control sintético reciente {i}"))
    item = RiskAwareContributionRepository(pg, PoisoningPolicy()).save(
        sample("Nuevo mensaje sintético de la clase concentrada")
    )
    assert "class_shift" in codes(pg, item.id)


def test_synthetic_normal_controls_false_marking_rate(pg, record_property):
    raw = PostgresContributionRepository(pg)

    def normal(i):
        return (
            "Control sintético de contenido diverso "
            + hashlib.sha256(f"synthetic-control-{i}".encode()).hexdigest()
        )

    for i in range(20):
        raw.save(sample(normal(i), "safe" if i % 2 else "smishing"))
    with pg.begin() as conn:
        conn.execute(
            text(
                "UPDATE contributions SET received_at = now() - interval '450 seconds'"
            )
        )
    repo = RiskAwareContributionRepository(pg, PoisoningPolicy())
    added = [
        repo.save(sample(normal(i), "safe" if i % 2 else "smishing"))
        for i in range(20, 40)
    ]
    marked = sum(bool(codes(pg, item.id)) for item in added)
    record_property("synthetic_false_marked", marked)
    record_property("synthetic_normal_total", len(added))
    assert marked == 0  # 0/20 on these controls only; not a population estimate.


def test_evaluation_signal_not_exposed_to_contributor(pg, caplog):
    repo = RiskAwareContributionRepository(
        pg, PoisoningPolicy(evaluation_references=(fingerprint(REFERENCE),))
    )
    app = create_app(Settings(api_key=SecretStr("synthetic-app")), repo)
    with TestClient(app, base_url="https://testserver") as client:
        response = client.post(
            "/api/v1/contributions",
            headers={"X-API-Key": "synthetic-app"},
            json={"text": REFERENCE, "label": "smishing", "model_version": "1.0.0"},
        )
    assert response.status_code == 201 and set(response.json()) == {"id", "status"}
    assert codes(pg) == {"evaluation_similarity"}
    assert REFERENCE not in caplog.text
    assert "192.0.2.42" not in caplog.text


def test_concurrent_burst_is_not_missed(pg):
    repo = RiskAwareContributionRepository(pg, PoisoningPolicy(similar_count=3))
    for i in range(2):
        repo.save(sample(REFERENCE + str(i)))
    with ThreadPoolExecutor(max_workers=2) as pool:
        items = list(pool.map(lambda i: repo.save(sample(REFERENCE + str(i))), [2, 3]))
    assert all(codes(pg, item.id) == {"similarity_burst"} for item in items)


def test_flag_failure_rolls_back_new_contribution_and_labels(pg):
    with pg.begin() as conn:
        conn.execute(
            text(
                "CREATE FUNCTION reject_synthetic_flag() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'synthetic flag failure'; END; $$ LANGUAGE plpgsql"
            )
        )
        conn.execute(
            text(
                "CREATE TRIGGER reject_synthetic_flag BEFORE INSERT ON risk_flags FOR EACH ROW EXECUTE FUNCTION reject_synthetic_flag()"
            )
        )
    repo = RiskAwareContributionRepository(
        pg, PoisoningPolicy(evaluation_references=(fingerprint(REFERENCE),))
    )
    with pytest.raises(DBAPIError):
        repo.save(sample(REFERENCE))
    with pg.connect() as conn:
        for table in [contributions, labels, model_versions, risk_flags]:
            assert conn.scalar(select(func.count()).select_from(table)) == 0
