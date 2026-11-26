from uuid import UUID

from sqlalchemy import Engine, case, exists, func, select, true, update

from smishing_backend.data.repositories.contribution_queries import automatic_label
from smishing_backend.data.schema import (
    contributions,
    labels,
    reviews,
    risk_flags,
)
from smishing_backend.domain.quarantine import Decision, InvalidTransition, Reason


class PostgresQuarantineRepository:
    def __init__(self, engine: Engine):
        self.engine = engine

    def review(self, contribution_id: UUID, decision: Decision, reason: Reason) -> None:
        with self.engine.begin() as connection:
            changed = connection.execute(
                update(contributions)
                .where(
                    contributions.c.id == contribution_id,
                    contributions.c.status == "pending",
                )
                .values(status=decision, reviewed_at=func.now(), review_reason=reason)
                .returning(contributions.c.id)
            ).scalar_one_or_none()
            if changed is None:
                raise InvalidTransition()

    def accepted_for_training(self) -> list[dict]:
        automatic = automatic_label()
        ranked = select(
            labels,
            func.row_number()
            .over(
                partition_by=labels.c.contribution_id,
                order_by=[
                    case((labels.c.origin == "manual", 0), else_=1),
                    labels.c.created_at.desc(),
                    labels.c.id.desc(),
                ],
            )
            .label("preference"),
        ).subquery()
        statement = (
            select(
                contributions.c.id,
                contributions.c.text,
                ranked.c.value.label("label"),
                ranked.c.origin.label("label_origin"),
                automatic.c.model_version,
            )
            .select_from(
                contributions.join(
                    ranked,
                    (ranked.c.contribution_id == contributions.c.id)
                    & (ranked.c.preference == 1),
                ).outerjoin(automatic, true())
            )
            .where(contributions.c.status == "accepted")
            .where(
                ~exists(
                    select(risk_flags.c.id).where(
                        risk_flags.c.contribution_id == contributions.c.id,
                        risk_flags.c.reviewed_at.is_(None),
                    )
                )
            )
        )
        with self.engine.connect() as connection:
            return [dict(row) for row in connection.execute(statement).mappings()]


    def reviewed_for_training(self, limit: int) -> tuple[list[dict], int]:
        automatic = automatic_label()
        manual = labels.alias("reviewed_label")
        unresolved = exists(select(risk_flags.c.id).where(
            risk_flags.c.contribution_id == contributions.c.id,
            risk_flags.c.reviewed_at.is_(None),
        ))
        are_accepted = contributions.c.status == "accepted"
        joined = (
            contributions.join(reviews, reviews.c.contribution_id == contributions.c.id)
            .join(manual, (manual.c.id == reviews.c.label_id) & (manual.c.contribution_id == contributions.c.id))
            .outerjoin(automatic, true())
        )
        eligible = select(
            contributions.c.text, manual.c.value.label("label"),
            manual.c.origin.label("label_origin"), automatic.c.model_version,
        ).select_from(joined).where(are_accepted, reviews.c.decision == "accepted",
            manual.c.origin == "manual", automatic.c.model_version.is_not(None), ~unresolved)
        # Read accepted total, exclusions and rows from the same consistent snapshot.
        with self.engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
            accepted = connection.scalar(select(func.count()).select_from(contributions).where(are_accepted))
            included = connection.scalar(select(func.count()).select_from(eligible.subquery()))
            rows = connection.execute(eligible.limit(limit + 1)).mappings()
            return [dict(row) for row in rows], (accepted or 0) - (included or 0)
