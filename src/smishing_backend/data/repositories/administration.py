"""Transactional management; terminal reviews and published facts are protected."""

import builtins
from uuid import uuid4

from sqlalchemy import Engine, delete, func, insert, select, update

from smishing_backend.data.model_release import read_github_publication
from smishing_backend.data.repositories.contribution_queries import (
    ContributionFilters,
    contribution_listing,
)
from smishing_backend.data.repositories.model_catalog import (
    PostgresModelCatalog,
    publication_values,
)
from smishing_backend.data.repositories.poisoning import (
    RiskAwareContributionRepository,
    flag_content,
    lock_risk_snapshot,
)
from smishing_backend.data.schema import contributions, labels, model_versions
from smishing_backend.domain.administration import ManagementError
from smishing_backend.domain.contributions import (
    Label,
    NewContribution,
    receive_contribution,
)
from smishing_backend.domain.poisoning import PoisoningPolicy
from smishing_backend.domain.privacy import assert_anonymized
from smishing_backend.domain.text import content_hash, normalize_text

TABLES = {
    "contributions": contributions,
    "message-labels": labels,
    "model-versions": model_versions,
}


def record(row):
    return dict(row._mapping)


class PostgresAdministrationRepository:
    def __init__(self, engine: Engine, policy: PoisoningPolicy):
        self.engine = engine
        self.risk = RiskAwareContributionRepository(engine, policy)

    def list(self, resource, limit, offset):
        table = TABLES[resource]
        with self.engine.connect() as conn:
            return [
                record(row)
                for row in conn.execute(
                    select(table).order_by(table.c.id).limit(limit).offset(offset)
                )
            ]

    def list_contributions(
        self, filters: ContributionFilters, limit: int, offset: int
    ) -> builtins.list[dict]:
        statement = contribution_listing(filters).limit(limit).offset(offset)
        with self.engine.connect() as conn:
            results = []
            for result in conn.execute(statement).mappings():
                if not result["model_version"] or not result["source"]:
                    raise ManagementError(503)
                results.append(
                    {**result, "risk_signals": sorted(result["risk_signals"] or [])}
                )
            return results

    def get(self, resource, identity):
        table = TABLES[resource]
        with self.engine.connect() as conn:
            row = conn.execute(select(table).where(table.c.id == identity)).first()
            if row is None:
                raise ManagementError(404)
            return record(row)

    def create(self, resource, values):
        if resource == "model-versions":
            identity = PostgresModelCatalog(self.engine).register(
                read_github_publication(values["release_tag"])
            )
        elif resource == "contributions":
            body = normalize_text(values["text"])
            saved = receive_contribution(
                NewContribution(
                    body,
                    content_hash(body),
                    (Label(values["label"], values["model_version"]),),
                ),
                self.risk,
            )
            identity = saved.id
        else:
            identity = uuid4()
            with self.engine.begin() as conn:
                lock_risk_snapshot(conn)
                self._pending(conn, values["message_id"])
                fields = self._label_fields(conn, values)
                conn.execute(insert(labels).values(id=identity, **fields))
        return self.get(resource, identity)

    @staticmethod
    def _pending(conn, identity):
        status = conn.scalar(
            select(contributions.c.status)
            .where(contributions.c.id == identity)
            .with_for_update()
        )
        if status is None:
            raise ManagementError(404)
        if status != "pending":
            raise ManagementError(409)

    @staticmethod
    def _label_fields(conn, values, own_id=None):
        if values["source"] == "device":
            if values["model_version_id"] is None or not conn.scalar(
                select(model_versions.c.id).where(
                    model_versions.c.id == values["model_version_id"]
                )
            ):
                raise ManagementError(422)
            existing = select(labels.c.id).where(
                labels.c.contribution_id == values["message_id"],
                labels.c.origin == "device",
            )
            if own_id is not None:
                existing = existing.where(labels.c.id != own_id)
            if conn.scalar(existing) is not None:
                raise ManagementError(409)
        elif values["model_version_id"] is not None:
            raise ManagementError(422)
        return dict(
            contribution_id=values["message_id"],
            value=values["category"],
            origin=values["source"],
            model_version_id=values["model_version_id"],
        )

    def change(self, resource, identity, values):
        publication = (
            read_github_publication(values["release_tag"])
            if resource == "model-versions"
            else None
        )
        table = TABLES[resource]
        with self.engine.begin() as conn:
            lock_risk_snapshot(conn)
            row = conn.execute(
                select(table).where(table.c.id == identity).with_for_update()
            ).first()
            if row is None:
                raise ManagementError(404)
            if resource == "contributions":
                self._pending(conn, identity)
                body = normalize_text(values["text"])
                assert_anonymized(body)
                # Reuse the ingestion detector with this record excluded from history.
                device = conn.execute(
                    select(labels.c.value, model_versions.c.version)
                    .join(model_versions)
                    .where(
                        labels.c.contribution_id == identity,
                        labels.c.origin == "device",
                    )
                ).first()
                if device is None:
                    raise ManagementError(409)
                item = NewContribution(
                    body, content_hash(body), (Label(device.value, device.version),)
                )
                codes = self.risk.assess_on_connection(conn, item, exclude=identity)
                conn.execute(
                    update(table)
                    .where(table.c.id == identity)
                    .values(text=body, content_hash=item.content_hash)
                )
                for code in codes:
                    flag_content(conn, identity, code)
            elif resource == "message-labels":
                self._pending(conn, row.contribution_id)
                merged = (
                    dict(
                        message_id=row.contribution_id,
                        category=row.value,
                        source=row.origin,
                        model_version_id=row.model_version_id,
                    )
                    | values
                )
                if (
                    merged["message_id"] != row.contribution_id
                    or merged["source"] != row.origin
                ):
                    raise ManagementError(409)
                fields = self._label_fields(conn, merged, identity)
                conn.execute(
                    update(table).where(table.c.id == identity).values(**fields)
                )
                # Any administrative label change must be examined in review.
                flag_content(conn, row.contribution_id, "label_conflict")
            else:
                if conn.scalar(
                    select(labels.c.id)
                    .where(labels.c.model_version_id == identity)
                    .limit(1)
                ):
                    raise ManagementError(409)
                assert publication is not None
                conn.execute(
                    update(table)
                    .where(table.c.id == identity)
                    .values(**publication_values(publication))
                )
        return self.get(resource, identity)

    def delete(self, resource, identity):
        table = TABLES[resource]
        with self.engine.begin() as conn:
            lock_risk_snapshot(conn)
            row = conn.execute(
                select(table).where(table.c.id == identity).with_for_update()
            ).first()
            if row is None:
                raise ManagementError(404)
            if resource == "message-labels":
                self._pending(conn, row.contribution_id)
                count = conn.scalar(
                    select(func.count())
                    .select_from(labels)
                    .where(labels.c.contribution_id == row.contribution_id)
                )
                if (count or 0) <= 1 or row.origin == "device":
                    raise ManagementError(409)
            conn.execute(delete(table).where(table.c.id == identity))
