from uuid import UUID, uuid4

from sqlalchemy import Engine, func, insert, select, true, update

from smishing_backend.data.repositories.contribution_queries import automatic_label
from smishing_backend.data.repositories.poisoning import lock_risk_snapshot
from smishing_backend.data.schema import contributions, labels, reviews, risk_flags
from smishing_backend.domain.quarantine import InvalidTransition
from smishing_backend.domain.review import RegisteredReview, ReviewAlreadyRecorded, ReviewDecision, ReviewExpectation


class PostgresReviewRepository:
    def __init__(self, engine: Engine):
        self.engine = engine

    def pending(self, limit: int) -> list[dict]:
        with self.engine.connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    select(
                        contributions.c.id,
                        contributions.c.text,
                        contributions.c.received_at,
                    )
                    .where(contributions.c.status == "pending")
                    .order_by(contributions.c.received_at, contributions.c.id)
                    .limit(limit)
                ).mappings()
            ]

    def decide(
        self, contribution_id: UUID, reviewer_id: str, decision: ReviewDecision,
        *, expectation: ReviewExpectation | None = None,
    ) -> RegisteredReview:
        review_id, label_id = uuid4(), uuid4()
        with self.engine.begin() as connection:
            lock_risk_snapshot(connection)
            if expectation is not None:
                automatic = automatic_label()
                row = connection.execute(
                    select(contributions.c.status, contributions.c.content_hash, automatic.c.model_version)
                    .select_from(contributions.outerjoin(automatic, true()))
                    .where(contributions.c.id == contribution_id)
                    .with_for_update(of=contributions)
                ).first()
                if row is None or row.content_hash != expectation.content_hash or row.model_version != expectation.model_version:
                    raise InvalidTransition()
                if row.status != "pending":
                    raise ReviewAlreadyRecorded()
            unresolved = connection.scalar(
                select(func.count())
                .select_from(risk_flags)
                .where(
                    risk_flags.c.contribution_id == contribution_id,
                    risk_flags.c.reviewed_at.is_(None),
                )
            )
            if unresolved and not decision.acknowledge_flags:
                raise InvalidTransition()
            reviewed_at = connection.execute(
                update(contributions)
                .where(
                    contributions.c.id == contribution_id,
                    contributions.c.status == "pending",
                )
                .values(
                    status=decision.decision,
                    review_reason=decision.reason,
                    reviewed_at=func.now(),
                )
                .returning(contributions.c.reviewed_at)
            ).scalar_one_or_none()
            if reviewed_at is None:
                raise InvalidTransition()
            connection.execute(
                insert(labels).values(
                    id=label_id,
                    contribution_id=contribution_id,
                    value=decision.label,
                    origin="manual",
                    model_version_id=None,
                    created_at=reviewed_at,
                )
            )
            connection.execute(
                insert(reviews).values(
                    id=review_id,
                    contribution_id=contribution_id,
                    label_id=label_id,
                    reviewer_id=reviewer_id,
                    decision=decision.decision,
                    reason=decision.reason,
                    reviewed_at=reviewed_at,
                )
            )
            if unresolved:
                connection.execute(
                    update(risk_flags)
                    .where(
                        risk_flags.c.contribution_id == contribution_id,
                        risk_flags.c.reviewed_at.is_(None),
                    )
                    .values(
                        reviewed_at=reviewed_at,
                        reviewer_id=reviewer_id,
                        review_decision=decision.decision,
                    )
                )
        return RegisteredReview(
            review_id,
            contribution_id,
            reviewer_id,
            decision.decision,
            reviewed_at,
            decision.label,
        )

    def flagged(self, limit: int) -> list[dict]:
        with self.engine.connect() as connection:
            statement = (
                select(
                    contributions.c.id,
                    contributions.c.text,
                    contributions.c.status.label("status"),
                    func.array_agg(risk_flags.c.code).label("signals"),
                )
                .join(risk_flags, risk_flags.c.contribution_id == contributions.c.id)
                .where(risk_flags.c.reviewed_at.is_(None))
                .group_by(contributions.c.id)
                .order_by(contributions.c.received_at, contributions.c.id)
                .limit(limit)
            )
            return [dict(row) for row in connection.execute(statement).mappings()]

    def acknowledge(self, contribution_id: UUID, reviewer_id: str) -> int:
        with self.engine.begin() as connection:
            lock_risk_snapshot(connection)
            status = connection.scalar(
                select(contributions.c.status)
                .where(contributions.c.id == contribution_id)
                .with_for_update()
            )
            if status not in {"accepted", "rejected"}:
                raise InvalidTransition()
            changed = connection.execute(
                update(risk_flags)
                .where(
                    risk_flags.c.contribution_id == contribution_id,
                    risk_flags.c.reviewed_at.is_(None),
                )
                .values(
                    reviewed_at=func.now(),
                    reviewer_id=reviewer_id,
                    review_decision="cleared",
                )
                .returning(risk_flags.c.id)
            ).all()
            return len(changed)
