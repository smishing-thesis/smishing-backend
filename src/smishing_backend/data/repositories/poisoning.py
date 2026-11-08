from datetime import timedelta
from uuid import uuid4

from sqlalchemy import Engine, func, select, text
from sqlalchemy.dialects.postgresql import insert

from smishing_backend.data.repositories.contributions import (
    PostgresContributionRepository,
)
from smishing_backend.data.schema import contributions, labels, risk_flags
from smishing_backend.domain.contributions import (
    DuplicateContribution,
    NewContribution,
    SavedContribution,
)
from smishing_backend.domain.poisoning import (
    ObservedContribution,
    PoisoningPolicy,
    assess,
)

RISK_LOCK_ID = 1397573971


def lock_risk_snapshot(connection):
    connection.execute(
        text("SELECT pg_advisory_xact_lock(:key)"), {"key": RISK_LOCK_ID}
    )


def flag_content(connection, contribution_id, code):
    connection.execute(
        insert(risk_flags)
        .values(id=uuid4(), contribution_id=contribution_id, code=code)
        .on_conflict_do_nothing(
            index_elements=[risk_flags.c.contribution_id, risk_flags.c.code],
            index_where=risk_flags.c.reviewed_at.is_(None),
        )
    )


class RiskAwareContributionRepository(PostgresContributionRepository):
    def __init__(self, engine: Engine, policy: PoisoningPolicy):
        super().__init__(engine)
        self.policy = policy

    def _save(self, contribution: NewContribution) -> SavedContribution:
        with self.engine.begin() as connection:
            lock_risk_snapshot(connection)
            existing = connection.execute(
                select(contributions.c.id, labels.c.value)
                .join(labels, labels.c.contribution_id == contributions.c.id)
                .where(
                    contributions.c.content_hash == contribution.content_hash,
                    labels.c.origin == "device",
                )
            ).all()
            if not existing:
                return self._store_new(connection, contribution)
            if any(row.value != contribution.labels[0].value for row in existing):
                flag_content(connection, existing[0].id, "label_conflict")
        # Commit the signal while holding the shared lock, then reject the duplicate.
        raise DuplicateContribution()

    def _store_new(
        self, connection, contribution: NewContribution
    ) -> SavedContribution:
        now = connection.execute(select(func.now())).scalar_one()
        split = now - timedelta(seconds=self.policy.window_seconds)
        rows = connection.execute(
            select(contributions.c.text, contributions.c.received_at, labels.c.value)
            .join(labels, labels.c.contribution_id == contributions.c.id)
            .where(
                labels.c.origin == "device",
                contributions.c.received_at
                >= split - timedelta(seconds=self.policy.window_seconds),
            )
            .order_by(contributions.c.received_at.desc(), contributions.c.id)
            .limit(self.policy.history_limit)
        ).all()
        recent = [
            ObservedContribution(row.text, row.value)
            for row in rows
            if row.received_at >= split
        ]
        baseline = [
            ObservedContribution(row.text, row.value)
            for row in rows
            if row.received_at < split
        ]
        codes = assess(
            contribution.text,
            contribution.labels[0].value,
            recent,
            baseline,
            self.policy,
        )
        saved = self._save_on_connection(connection, contribution)
        for code in codes:
            flag_content(connection, saved.id, code)
        return saved

    def save(self, contribution: NewContribution) -> SavedContribution:
        try:
            return super().save(contribution)
        except DuplicateContribution:
            # Never retain the rejected duplicate's text. Mark only the existing record.
            with self.engine.begin() as connection:
                lock_risk_snapshot(connection)
                existing = connection.execute(
                    select(contributions.c.id, labels.c.value)
                    .join(labels, labels.c.contribution_id == contributions.c.id)
                    .where(
                        contributions.c.content_hash == contribution.content_hash,
                        labels.c.origin == "device",
                    )
                ).all()
                if existing and any(
                    row.value != contribution.labels[0].value for row in existing
                ):
                    flag_content(connection, existing[0].id, "label_conflict")
            raise
