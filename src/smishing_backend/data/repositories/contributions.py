"""Atomic aggregate persistence using PostgreSQL, hidden behind a domain port."""

from uuid import uuid4

from sqlalchemy import Engine, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from smishing_backend.data.schema import contributions, labels, model_versions
from smishing_backend.domain.contributions import (
    DuplicateContribution,
    NewContribution,
    SavedContribution,
)


class PostgresContributionRepository:
    def __init__(self, engine: Engine):
        self.engine = engine

    def save(self, contribution: NewContribution) -> SavedContribution:
        try:
            return self._save(contribution)
        except IntegrityError as exc:
            diagnostic = getattr(exc.orig, "diag", None)
            if (
                getattr(diagnostic, "constraint_name", None)
                == "uq_contributions_content_hash"
            ):
                raise DuplicateContribution() from None
            raise

    def _save(self, contribution: NewContribution) -> SavedContribution:
        with self.engine.begin() as connection:
            return self._save_on_connection(connection, contribution)

    def _save_on_connection(
        self, connection, contribution: NewContribution
    ) -> SavedContribution:
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
                    .on_conflict_do_nothing(index_elements=[model_versions.c.version])
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
                    origin=label.origin,
                )
            )
        return SavedContribution(row.id, row.status, row.received_at)
