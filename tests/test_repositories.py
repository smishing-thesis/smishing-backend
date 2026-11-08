import ast
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from smishing_backend.data.repositories.contributions import (
    PostgresContributionRepository,
)
from smishing_backend.data.schema import contributions, labels, model_versions
from smishing_backend.domain.contributions import (
    Label,
    NewContribution,
    receive_contribution,
)


def sample(digest="a" * 64, values=None):
    return NewContribution(
        "Mensaje sintético [URL]", digest, values or (Label("smishing", "1.0.0"),)
    )


def count(conn, table):
    return conn.scalar(select(func.count()).select_from(table))


def test_atomic_save_and_reuse_version(pg):
    repo = PostgresContributionRepository(pg)
    first = receive_contribution(
        sample(values=(Label("safe", "1.0.0"), Label("smishing", None, "manual"))), repo
    )
    second = receive_contribution(sample("b" * 64), repo)
    assert first.id != second.id
    assert first.status == "pending"
    assert first.received_at.tzinfo is not None
    with pg.connect() as conn:
        assert count(conn, contributions) == 2
        assert count(conn, labels) == 3
        assert count(conn, model_versions) == 1
        assert (
            conn.scalar(
                select(labels.c.model_version_id).where(labels.c.value == "safe")
            )
            is not None
        )


def test_failure_in_second_label_rolls_back_everything(pg):
    repo = PostgresContributionRepository(pg)
    with pytest.raises(IntegrityError):
        repo.save(sample(values=(Label("safe", "1.0.0"), Label("invalid", "2.0.0"))))
    with pg.connect() as conn:
        assert all(
            count(conn, table) == 0 for table in [contributions, labels, model_versions]
        )


def test_shared_version_concurrently(pg):
    repo = PostgresContributionRepository(pg)
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(lambda h: repo.save(sample(h)), ["a" * 64, "b" * 64]))
    assert len({row.id for row in rows}) == 2
    with pg.connect() as conn:
        assert count(conn, model_versions) == 1


def test_domain_import_boundaries():
    for path in Path("src/smishing_backend/domain").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith(
                    ("fastapi", "sqlalchemy", "smishing_backend.data")
                )
            elif isinstance(node, ast.Import):
                assert all(
                    not name.name.startswith(
                        ("fastapi", "sqlalchemy", "smishing_backend.data")
                    )
                    for name in node.names
                )
