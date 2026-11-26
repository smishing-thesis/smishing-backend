import copy
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from uuid import uuid4

import pytest
from conftest import migrate
from sqlalchemy import func, insert, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from smishing_backend.data.model_release import (
    parse_publication,
    read_github_publication,
)
from smishing_backend.data.repositories.contributions import (
    PostgresContributionRepository,
)
from smishing_backend.data.repositories.labels import PostgresLabelRepository
from smishing_backend.data.repositories.model_catalog import PostgresModelCatalog
from smishing_backend.data.repositories.quarantine import PostgresQuarantineRepository
from smishing_backend.data.schema import contributions, labels, model_versions
from smishing_backend.domain.contributions import Label, NewContribution
from smishing_backend.domain.model_catalog import (
    InvalidModelPublication,
    ModelVersionConflict,
)
from smishing_backend.domain.quarantine import register_review


def test_publication_keeps_only_catalog_facts(published_metadata):
    publication = parse_publication(*published_metadata)
    assert publication.version == "1.0.0"
    assert publication.trained_at.tzinfo is not None
    assert publication.corpus_version == "synthetic-1"
    assert publication.hyperparameters["epochs"] == 2
    assert publication.metrics["validation"]["tp"] == 1
    assert "SYNTHETIC_PRIVATE" not in repr(publication)
    assert len(publication.metadata_sha256) == 64


@pytest.mark.parametrize(
    "change",
    [
        "wrong_version",
        "wrong_hash",
        "missing_metric",
        "nan",
        "bad_date",
        "wrong_repo",
        "draft",
        "path_as_corpus",
    ],
)
def test_invalid_publications_are_generic(published_metadata, change):
    release, training, evaluation = copy.deepcopy(published_metadata)
    if change == "wrong_version":
        evaluation["model_version"] = "2.0.0"
    if change == "wrong_hash":
        evaluation["model_sha256"] = "c" * 64
    if change == "missing_metric":
        del evaluation["validation_metrics_at_threshold"]["tp"]
    if change == "nan":
        evaluation["threshold"] = float("nan")
    if change == "bad_date":
        training["trained_at"] = "2026-01-01T00:00:00"
    if change == "wrong_repo":
        release["html_url"] = "https://example.invalid/release"
    if change == "draft":
        release["draft"] = True
    if change == "path_as_corpus":
        training["corpus_version"] = "/private/SYNTHETIC_PRIVATE_PATH"
    with pytest.raises(
        InvalidModelPublication, match="Invalid or inconsistent"
    ) as error:
        parse_publication(release, training, evaluation)
    assert "SYNTHETIC_PRIVATE" not in str(error.value)


def test_reader_uses_only_fixed_repository_metadata(monkeypatch, published_metadata):
    from smishing_backend.data import model_release

    release, training, evaluation = published_metadata
    release = {
        **release,
        "assets": [
            {"id": 11, "name": "training_metadata.json"},
            {"id": 12, "name": "evaluation.json"},
            {"id": 13, "name": "model.tflite"},
        ],
    }
    calls = []

    def read(endpoint, asset=False):
        calls.append((endpoint, asset))
        if endpoint.endswith("/tags/v1.0.0"):
            return release
        return {11: training, 12: evaluation}[int(endpoint.rsplit("/", 1)[1])]

    monkeypatch.setattr(model_release, "_gh_json", read)
    assert read_github_publication("v1.0.0").version == "1.0.0"
    assert len(calls) == 3 and all(
        "smishing-thesis/charcnn-smishing-model" in p for p, _ in calls
    )
    assert not any(p.endswith("13") for p, _ in calls)
    with pytest.raises(InvalidModelPublication):
        read_github_publication("../arbitrary")


def test_register_reuses_registered_publication_idempotently(pg, published_metadata):
    cid = (
        PostgresContributionRepository(pg)
        .save(NewContribution("Mensaje sintético", "a" * 64, (Label("safe", "1.0.0"),)))
        .id
    )
    with pg.connect() as conn:
        original = conn.scalar(
            select(labels.c.model_version_id).where(labels.c.contribution_id == cid)
        )
    publication = parse_publication(*published_metadata)
    catalog = PostgresModelCatalog(pg)
    assert catalog.register(publication) == original
    assert catalog.register(publication) == original
    with pg.connect() as conn:
        row = conn.execute(select(model_versions)).one()
        assert row.corpus_version == "synthetic-1" and row.release_tag == "v1.0.0"
        assert "SYNTHETIC_PRIVATE" not in json.dumps(dict(row._mapping), default=str)
        assert conn.scalar(select(func.count()).select_from(model_versions)) == 1
    with pytest.raises(ModelVersionConflict):
        catalog.register(replace(publication, metadata_sha256="c" * 64))


def test_concurrent_registration_same_publication(pg, published_metadata):
    catalog = PostgresModelCatalog(pg)
    publication = parse_publication(*published_metadata)
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(catalog.register, [publication, publication]))
    assert ids[0] == ids[1]


def test_manual_and_device_labels_coexist_and_manual_wins(pg):
    cid = (
        PostgresContributionRepository(pg)
        .save(
            NewContribution(
                "Mensaje sintético", "a" * 64, (Label("smishing", "1.0.0"),)
            )
        )
        .id
    )
    repository = PostgresLabelRepository(pg)
    assert repository.verified(cid) == []
    repository.add_manual(cid, "safe")
    verified = repository.verified(cid)
    assert len(verified) == 1 and verified[0]["value"] == "safe"
    assert verified[0]["origin"] == "manual" and verified[0]["model_version_id"] is None
    quarantine = PostgresQuarantineRepository(pg)
    register_review(cid, "accepted", "quality_checked", quarantine)
    training = quarantine.accepted_for_training()
    assert len(training) == 1 and training[0]["label"] == "safe"
    assert (
        training[0]["label_origin"] == "manual"
        and training[0]["model_version"] == "1.0.0"
    )
    with pg.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(labels)) == 2


@pytest.mark.parametrize(
    "origin,version", [("device", None), ("manual", "model"), ("unknown", None)]
)
def test_database_provenance_constraints(pg, origin, version):
    cid, mid = uuid4(), uuid4()
    with pg.begin() as conn:
        conn.execute(
            insert(contributions).values(
                id=cid, text="Sintético", content_hash="a" * 64
            )
        )
        mid = conn.scalar(select(model_versions.c.id))
    with pytest.raises(IntegrityError), pg.begin() as conn:
        conn.execute(
            insert(labels).values(
                id=uuid4(),
                contribution_id=cid,
                value="safe",
                origin=origin,
                model_version_id=mid if version else None,
            )
        )


def test_upgrade_preserves_device_labels_and_refuses_unknown_legacy_origin(empty_pg):
    migrate(empty_pg, "0002")
    cid, mid = uuid4(), uuid4()
    with empty_pg.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO contributions(id,text,content_hash) VALUES (:id,'Sintético',:hash)"
            ),
            {"id": cid, "hash": "a" * 64},
        )
        conn.execute(
            text("INSERT INTO model_versions(id,version) VALUES (:id,'1.0.0')"),
            {"id": mid},
        )
        conn.execute(
            text(
                "INSERT INTO labels(id,contribution_id,value) VALUES (:id,:cid,'safe')"
            ),
            {"id": uuid4(), "cid": cid},
        )
    with pytest.raises(DBAPIError, match="Reconcile legacy label provenance"):
        migrate(empty_pg)
    with empty_pg.begin() as conn:
        assert conn.scalar(text("SELECT version_num FROM alembic_version")) == "0002"
        conn.execute(text("UPDATE labels SET model_version_id=:id"), {"id": mid})
    migrate(empty_pg, "0003")
    with empty_pg.connect() as conn:
        assert conn.scalar(text("SELECT origin FROM labels")) == "device"
        assert conn.scalar(text("SELECT model_version_id FROM labels")) == mid
