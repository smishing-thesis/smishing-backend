from uuid import UUID

from sqlalchemy import Engine, case, exists, func, select, update

from smishing_backend.data.schema import (
    contributions,
    labels,
    model_versions,
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
                model_versions.c.version.label("model_version"),
            )
            .select_from(
                contributions.join(
                    ranked,
                    (ranked.c.contribution_id == contributions.c.id)
                    & (ranked.c.preference == 1),
                ).outerjoin(
                    model_versions, ranked.c.model_version_id == model_versions.c.id
                )
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
