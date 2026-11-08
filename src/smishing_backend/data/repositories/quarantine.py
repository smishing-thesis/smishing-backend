from uuid import UUID

from sqlalchemy import Engine, func, select, update

from smishing_backend.data.schema import contributions, labels, model_versions
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
        statement = (
            select(
                contributions.c.id,
                contributions.c.text,
                labels.c.value.label("label"),
                model_versions.c.version.label("model_version"),
            )
            .select_from(
                contributions.join(
                    labels, labels.c.contribution_id == contributions.c.id
                ).outerjoin(
                    model_versions, labels.c.model_version_id == model_versions.c.id
                )
            )
            .where(contributions.c.status == "accepted")
        )
        with self.engine.connect() as connection:
            return [dict(row) for row in connection.execute(statement).mappings()]
