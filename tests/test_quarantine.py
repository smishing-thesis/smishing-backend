from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from smishing_backend.data.repositories.contributions import (
    PostgresContributionRepository,
)
from smishing_backend.data.repositories.quarantine import PostgresQuarantineRepository
from smishing_backend.data.schema import contributions
from smishing_backend.domain.contributions import Label, NewContribution
from smishing_backend.domain.quarantine import InvalidTransition, register_review


def save(pg, digest="a" * 64):
    return PostgresContributionRepository(pg).save(
        NewContribution("Mensaje sintético", digest, (Label("safe", "1.0.0"),))
    )


def test_only_reviewed_accepted_reach_training(pg):
    repo = PostgresQuarantineRepository(pg)
    accepted, rejected, pending = [save(pg, c * 64) for c in "abc"]
    assert repo.accepted_for_training() == []
    register_review(accepted.id, "accepted", "quality_checked", repo)
    register_review(rejected.id, "rejected", "invalid_content", repo)
    rows = repo.accepted_for_training()
    assert [row["id"] for row in rows] == [accepted.id]
    with pg.connect() as conn:
        record = conn.execute(
            select(contributions).where(contributions.c.id == accepted.id)
        ).one()
        assert record.reviewed_at.tzinfo is not None
        assert record.review_reason == "quality_checked"
        assert (
            conn.scalar(
                select(contributions.c.status).where(contributions.c.id == pending.id)
            )
            == "pending"
        )


@pytest.mark.parametrize(
    "decision,reason",
    [("pending", "quality_checked"), ("accepted", ""), ("accepted", "free text")],
)
def test_invalid_review(pg, decision, reason):
    item = save(pg)
    with pytest.raises(InvalidTransition):
        register_review(item.id, decision, reason, PostgresQuarantineRepository(pg))


def test_terminal_and_missing_transitions(pg):
    item = save(pg)
    repo = PostgresQuarantineRepository(pg)
    register_review(item.id, "accepted", "quality_checked", repo)
    for cid in [item.id, uuid4()]:
        with pytest.raises(InvalidTransition):
            register_review(cid, "rejected", "invalid_content", repo)
    with pytest.raises(IntegrityError), pg.begin() as conn:
        conn.execute(
            update(contributions)
            .where(contributions.c.id == item.id)
            .values(status="rejected")
        )


@pytest.mark.parametrize(
    "fields",
    [
        {"status": "accepted"},
        {"status": "accepted", "reviewed_at": func.now()},
        {"status": "rejected", "review_reason": "invalid_content"},
    ],
)
def test_database_requires_registered_review(pg, fields):
    item = save(pg)
    with pytest.raises(IntegrityError), pg.begin() as conn:
        conn.execute(
            update(contributions).where(contributions.c.id == item.id).values(**fields)
        )


def test_concurrent_review_only_one_wins(pg):
    item = save(pg)
    repo = PostgresQuarantineRepository(pg)

    def decide(decision):
        try:
            register_review(item.id, decision, "quality_checked", repo)
            return True
        except InvalidTransition:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(decide, ["accepted", "rejected"])) == [False, True]
