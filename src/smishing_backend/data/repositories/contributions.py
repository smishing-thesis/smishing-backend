"""Atomic aggregate persistence using PostgreSQL, hidden behind a domain port."""

from uuid import uuid4

from sqlalchemy import Engine, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from smishing_backend.data.schema import contributions, labels, model_versions
from smishing_backend.domain.contributions import NewContribution, SavedContribution


class PostgresContributionRepository:
    def __init__(self, engine: Engine):
        self.engine = engine

    def save(self, contribution: NewContribution) -> SavedContribution:
        # begin commits only after all labels succeed; any failure rolls back all rows.
        with self.engine.begin() as connection:
            row = connection.execute(
                insert(contributions)
                .values(
                    id=uuid4(),
                    text=contribution.text,
                    content_hash=contribution.content_hash,
                )
                .returning(
                    contributions.c.id,
                    contributions.c.status,
                    contributions.c.received_at,
                )
            ).one()
            for label in contribution.labels:
                model_id = None
                if label.model_version is not None:
                    model_id = connection.execute(
                        pg_insert(model_versions)
                        .values(id=uuid4(), version=label.model_version)
                        .on_conflict_do_nothing(
                            index_elements=[model_versions.c.version]
                        )
                        .returning(model_versions.c.id)
                    ).scalar_one_or_none()
                    if model_id is None:
                        model_id = connection.execute(
                            select(model_versions.c.id).where(
                                model_versions.c.version == label.model_version
                            )
                        ).scalar_one()
                connection.execute(
                    insert(labels).values(
                        id=uuid4(),
                        contribution_id=row.id,
                        model_version_id=model_id,
                        value=label.value,
                    )
                )
        return SavedContribution(row.id, row.status, row.received_at)
