from uuid import UUID, uuid4

from sqlalchemy import Engine, func, insert, select, update

from smishing_backend.data.schema import contributions, labels, reviews
from smishing_backend.domain.quarantine import InvalidTransition
from smishing_backend.domain.review import RegisteredReview, ReviewDecision


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
        self, contribution_id: UUID, reviewer_id: str, decision: ReviewDecision
    ) -> RegisteredReview:
        review_id, label_id = uuid4(), uuid4()
        with self.engine.begin() as connection:
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
        return RegisteredReview(
            review_id,
            contribution_id,
            reviewer_id,
            decision.decision,
            reviewed_at,
            decision.label,
        )
