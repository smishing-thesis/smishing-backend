from uuid import uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from conftest import migrate
from sqlalchemy import insert, inspect
from sqlalchemy.exc import IntegrityError

from smishing_backend.data.schema import contributions, labels, metadata, model_versions


def test_upgrade_downgrade_upgrade(empty_pg):
    migrate(empty_pg)
    assert set(inspect(empty_pg).get_table_names()) == {
        "alembic_version",
        "contributions",
        "labels",
        "model_versions",
    }
    with empty_pg.connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn), metadata) == []
    migrate(empty_pg, "base", downgrade=True)
    assert inspect(empty_pg).get_table_names() == ["alembic_version"]
    migrate(empty_pg)
    assert "contributions" in inspect(empty_pg).get_table_names()


@pytest.mark.parametrize(
    "change",
    [
        {"status": "unknown"},
        {"text": ""},
        {"text": "x" * 2049},
        {"content_hash": "wrong"},
        {"text": None},
    ],
)
def test_contribution_constraints(pg, change):
    with pytest.raises(IntegrityError), pg.begin() as conn:
        conn.execute(
            insert(contributions).values(
                id=uuid4(), **({"text": "Sintético", "content_hash": "a" * 64} | change)
            )
        )


def test_unique_hash_and_pending(pg):
    with pg.begin() as conn:
        result = conn.execute(
            insert(contributions)
            .values(id=uuid4(), text="Sintético", content_hash="a" * 64)
            .returning(contributions.c.status, contributions.c.received_at)
        ).one()
        assert result.status == "pending"
        assert result.received_at.tzinfo is not None
    with pytest.raises(IntegrityError), pg.begin() as conn:
        conn.execute(
            insert(contributions).values(
                id=uuid4(), text="Sintético", content_hash="a" * 64
            )
        )


def test_label_foreign_keys_optional_version_and_values(pg):
    cid, mid = uuid4(), uuid4()
    with pg.begin() as conn:
        conn.execute(
            insert(contributions).values(
                id=cid, text="Sintético", content_hash="b" * 64
            )
        )
        conn.execute(insert(model_versions).values(id=mid, version="1.0.0"))
        conn.execute(
            insert(labels),
            [
                {
                    "id": uuid4(),
                    "contribution_id": cid,
                    "model_version_id": None,
                    "origin": "manual",
                    "value": "safe",
                },
                {
                    "id": uuid4(),
                    "contribution_id": cid,
                    "model_version_id": mid,
                    "origin": "device",
                    "value": "smishing",
                },
            ],
        )
    for changes in [
        {"contribution_id": uuid4()},
        {"model_version_id": uuid4()},
        {"value": "unknown"},
    ]:
        with pytest.raises(IntegrityError), pg.begin() as conn:
            conn.execute(
                insert(labels).values(
                    **(
                        {"id": uuid4(), "contribution_id": cid, "value": "safe"}
                        | changes
                    )
                )
            )
