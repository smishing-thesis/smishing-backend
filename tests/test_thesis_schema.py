"""Verify the actual physical schema and migration against Memoria, Figure 6."""

from dataclasses import asdict
from decimal import Decimal
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from conftest import migrate
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.exc import IntegrityError

from smishing_backend.config import Settings
from smishing_backend.data.model_release import parse_publication
from smishing_backend.data.repositories.contributions import (
    PostgresContributionRepository,
)
from smishing_backend.data.schema import contributions, metadata, model_versions
from smishing_backend.main import create_app


def test_figure_6_names_types_required_fields_and_relations(pg):
    inspector = sa.inspect(pg)
    expected = {
        "contributed_message": {
            "id": "UUID",
            "text": "TEXT",
            "content_hash": "CHAR(64)",
            "received_at": "TIMESTAMP",
            "review_status": "VARCHAR(20)",
        },
        "message_label": {
            "id": "UUID",
            "message_id": "UUID",
            "category": "VARCHAR(20)",
            "source": "VARCHAR(20)",
            "model_version_id": "UUID",
            "created_at": "TIMESTAMP",
        },
        "model_version": {
            "id": "UUID",
            "version_tag": "VARCHAR(20)",
            "generated_at": "TIMESTAMP",
            "training_set": "VARCHAR(100)",
            "hyperparameters": "TEXT",
            "accuracy": "NUMERIC(5, 4)",
            "precision_score": "NUMERIC(5, 4)",
            "recall": "NUMERIC(5, 4)",
            "f1_score": "NUMERIC(5, 4)",
        },
    }
    for table, fields in expected.items():
        columns = {column["name"]: column for column in inspector.get_columns(table)}
        assert fields.keys() <= columns.keys()
        for name, expected_type in fields.items():
            assert str(columns[name]["type"]) == expected_type
            assert columns[name]["nullable"] is (name == "model_version_id")
            if expected_type == "TIMESTAMP":
                assert columns[name]["type"].timezone
        assert inspector.get_pk_constraint(table)["constrained_columns"] == ["id"]
    relations = {
        (tuple(fk["constrained_columns"]), fk["referred_table"])
        for fk in inspector.get_foreign_keys("message_label")
    }
    assert (("message_id",), "contributed_message") in relations
    assert (("model_version_id",), "model_version") in relations
    for table, column in [
        ("contributed_message", "content_hash"),
        ("model_version", "version_tag"),
    ]:
        assert any(
            constraint["column_names"] == [column]
            for constraint in inspector.get_unique_constraints(table)
        )
    with pg.connect() as conn:
        model = conn.execute(sa.select(model_versions)).one()
        assert model.accuracy == Decimal("0.8000")
        assert compare_metadata(MigrationContext.configure(conn), metadata) == []


def test_unknown_publication_returns_generic_422_without_partial_insert(pg):
    app = create_app(
        Settings(api_key=SecretStr("synthetic-app")), PostgresContributionRepository(pg)
    )
    with TestClient(app, base_url="https://testserver") as client:
        payload = {
            "text": "Aporte sintético <URL>",
            "label": "safe",
            "model_version": "9.9.9",
        }
        response = client.post(
            "/api/v1/contributions",
            headers={"X-API-Key": "synthetic-app"},
            json=payload,
        )
        assert response.status_code == 422
        assert payload["text"] not in response.text and "9.9.9" not in response.text
        assert (
            client.post(
                "/api/v1/contributions",
                headers={"X-API-Key": "synthetic-app"},
                json={**payload, "model_version": "1.0.0-" + "x" * 15},
            ).status_code
            == 422
        )
    with pg.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(contributions)) == 0
        assert conn.scalar(sa.select(sa.func.count()).select_from(model_versions)) == 1


def test_incomplete_catalog_cannot_be_inserted(pg):
    with pytest.raises(IntegrityError), pg.begin() as conn:
        conn.execute(sa.insert(model_versions).values(id=uuid4(), version="9.9.9"))


def test_existing_data_survives_upgrade_downgrade_and_quarantine_still_holds(
    empty_pg, published_metadata
):
    migrate(empty_pg, "0004")
    old = sa.MetaData()
    old.reflect(empty_pg)
    cid, automatic, manual, model_id, review_id = [uuid4() for _ in range(5)]
    facts = asdict(parse_publication(*published_metadata))
    with empty_pg.begin() as conn:
        conn.execute(
            sa.insert(old.tables["model_versions"]).values(id=model_id, **facts)
        )
        conn.execute(
            sa.insert(old.tables["contributions"]).values(
                id=cid,
                text="Aporte sintético <URL>",
                content_hash="a" * 64,
                status="accepted",
                reviewed_at=sa.func.now(),
                review_reason="quality_checked",
            )
        )
        conn.execute(
            sa.insert(old.tables["labels"]),
            [
                {
                    "id": automatic,
                    "contribution_id": cid,
                    "model_version_id": model_id,
                    "value": "smishing",
                    "origin": "device",
                },
                {
                    "id": manual,
                    "contribution_id": cid,
                    "model_version_id": None,
                    "value": "safe",
                    "origin": "manual",
                },
            ],
        )
        conn.execute(
            sa.insert(old.tables["reviews"]).values(
                id=review_id,
                contribution_id=cid,
                label_id=manual,
                reviewer_id="reviewer-demo",
                decision="accepted",
                reason="quality_checked",
                reviewed_at=sa.func.now(),
            )
        )
    migrate(empty_pg)
    with empty_pg.connect() as conn:
        assert conn.execute(
            sa.text(
                "SELECT id, text, content_hash, review_status FROM contributed_message"
            )
        ).one() == (cid, "Aporte sintético <URL>", "a" * 64, "accepted")
        assert (
            conn.scalar(
                sa.text("SELECT count(*) FROM message_label WHERE message_id=:cid"),
                {"cid": cid},
            )
            == 2
        )
        assert (
            conn.scalar(
                sa.text("SELECT label_id FROM reviews WHERE id=:id"), {"id": review_id}
            )
            == manual
        )
        assert conn.scalar(sa.text("SELECT accuracy FROM model_version")) == Decimal(
            "0.8000"
        )
    with pytest.raises(IntegrityError), empty_pg.begin() as conn:
        conn.execute(
            sa.text(
                "UPDATE contributed_message SET review_status='rejected' WHERE id=:id"
            ),
            {"id": cid},
        )
    migrate(empty_pg, "0004", downgrade=True)
    with empty_pg.connect() as conn:
        assert (
            conn.scalar(
                sa.text("SELECT status FROM contributions WHERE id=:id"), {"id": cid}
            )
            == "accepted"
        )
        restored = conn.execute(
            sa.text("SELECT hyperparameters, metrics FROM model_versions")
        ).one()
        assert (
            restored.hyperparameters == facts["hyperparameters"]
            and restored.metrics == facts["metrics"]
        )
        assert conn.scalar(sa.text("SELECT count(*) FROM labels")) == 2
    with pytest.raises(IntegrityError), empty_pg.begin() as conn:
        conn.execute(
            sa.text("UPDATE contributions SET status='rejected' WHERE id=:id"),
            {"id": cid},
        )
    migrate(empty_pg)
    with empty_pg.connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn), metadata) == []


def test_incomplete_legacy_model_aborts_before_schema_changes(empty_pg):
    migrate(empty_pg, "0004")
    with empty_pg.begin() as conn:
        conn.execute(
            sa.text("INSERT INTO model_versions(id,version) VALUES (:id,'9.9.9')"),
            {"id": uuid4()},
        )
    with pytest.raises(RuntimeError, match="Reconcile model publication metadata"):
        migrate(empty_pg)
    with empty_pg.connect() as conn:
        assert conn.scalar(sa.text("SELECT version_num FROM alembic_version")) == "0004"
        assert conn.scalar(sa.text("SELECT count(*) FROM model_versions")) == 1
    assert "contributions" in sa.inspect(empty_pg).get_table_names()
    assert "contributed_message" not in sa.inspect(empty_pg).get_table_names()


def test_operator_can_fill_legacy_reference_before_upgrade(
    empty_pg, published_metadata, monkeypatch, capsys
):
    from smishing_backend import catalog

    migrate(empty_pg, "0004")
    model_id = uuid4()
    with empty_pg.begin() as conn:
        conn.execute(
            sa.text("INSERT INTO model_versions(id,version) VALUES (:id,'1.0.0')"),
            {"id": model_id},
        )
    monkeypatch.setattr(catalog, "create_database_engine", lambda _: empty_pg)
    monkeypatch.setattr(
        catalog,
        "read_github_publication",
        lambda _: parse_publication(*published_metadata),
    )
    monkeypatch.setattr(
        "sys.argv", ["catalog", "--release", "v1.0.0", "--prepare-schema-0005"]
    )
    assert catalog.main() == 0
    assert catalog.main() == 0
    assert "registered" in capsys.readouterr().out
    migrate(empty_pg)
    with empty_pg.connect() as conn:
        assert conn.scalar(sa.select(model_versions.c.id)) == model_id
        assert conn.scalar(sa.select(sa.func.count()).select_from(model_versions)) == 1
    # Explicit preparation mode must fail closed on an already upgraded database.
    assert catalog.main() == 1


@pytest.mark.parametrize(
    "change", ["long_version", "long_training_set", "missing_metric", "invalid_metric"]
)
def test_incompatible_legacy_values_are_rejected_without_truncation(
    empty_pg, published_metadata, change
):
    migrate(empty_pg, "0004")
    old_model = sa.Table("model_versions", sa.MetaData(), autoload_with=empty_pg)
    facts = asdict(parse_publication(*published_metadata))
    if change == "long_version":
        facts["version"] = "1.0.0-" + "x" * 16
    elif change == "long_training_set":
        facts["corpus_version"] = "x" * 101
    elif change == "missing_metric":
        del facts["metrics"]["validation"]["f1"]
    else:
        facts["metrics"]["validation"]["f1"] = 1.1
    with empty_pg.begin() as conn:
        conn.execute(sa.insert(old_model).values(id=uuid4(), **facts))
    with pytest.raises(RuntimeError, match="Reconcile model publication"):
        migrate(empty_pg)
    with empty_pg.connect() as conn:
        assert conn.scalar(sa.text("SELECT version_num FROM alembic_version")) == "0004"
        assert (
            conn.scalar(sa.text("SELECT version FROM model_versions"))
            == facts["version"]
        )
        assert (
            conn.scalar(sa.text("SELECT corpus_version FROM model_versions"))
            == facts["corpus_version"]
        )
