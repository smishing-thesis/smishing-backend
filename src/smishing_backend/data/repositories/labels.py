from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import Engine, insert, select

from smishing_backend.data.schema import labels
from smishing_backend.domain.contributions import Label


class PostgresLabelRepository:
    def __init__(self, engine: Engine):
        self.engine = engine

    def add_manual(
        self, contribution_id: UUID, value: Literal["safe", "smishing"]
    ) -> UUID:
        label = Label(value, None, "manual")
        label_id = uuid4()
        with self.engine.begin() as connection:
            connection.execute(
                insert(labels).values(
                    id=label_id,
                    contribution_id=contribution_id,
                    value=label.value,
                    origin=label.origin,
                    model_version_id=None,
                )
            )
        return label_id

    def verified(self, contribution_id: UUID) -> list[dict]:
        with self.engine.connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    select(*(column.label(column.key) for column in labels.c))
                    .where(
                        labels.c.contribution_id == contribution_id,
                        labels.c.origin == "manual",
                    )
                    .order_by(labels.c.created_at, labels.c.id)
                ).mappings()
            ]
