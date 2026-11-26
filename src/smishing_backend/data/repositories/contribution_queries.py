"""Shared management projection and filters for listings and spreadsheet exports."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import case, func, select, true

from smishing_backend.data.schema import contributions, labels, model_versions, risk_flags


@dataclass(frozen=True)
class ContributionFilters:
    status: str | None = None
    received_from: datetime | None = None
    received_to: datetime | None = None
    reviewed_from: datetime | None = None
    reviewed_to: datetime | None = None
    category: str | None = None
    source: str | None = None
    model_version: str | None = None
    reason: str | None = None
    has_risk: bool | None = None
    order: str = "desc"


def automatic_label():
    """The first device label is the one recorded at ingestion."""
    return (
        select(labels.c.value.label("automatic_label"), model_versions.c.version.label("model_version"))
        .join(model_versions)
        .where(labels.c.contribution_id == contributions.c.id, labels.c.origin == "device")
        .order_by(labels.c.created_at, labels.c.id)
        .limit(1)
        .correlate(contributions)
        .lateral("automatic")
    )


def contribution_listing(filters: ContributionFilters):
    automatic = automatic_label()
    current = (
        select(labels.c.value.label("category"), labels.c.origin.label("source"))
        .where(labels.c.contribution_id == contributions.c.id)
        .order_by(case((labels.c.origin == "manual", 0), else_=1), labels.c.created_at.desc(), labels.c.id.desc())
        .limit(1)
        .correlate(contributions)
        .lateral("current_label")
    )
    flags = (
        select(func.array_agg(risk_flags.c.code))
        .where(risk_flags.c.contribution_id == contributions.c.id, risk_flags.c.reviewed_at.is_(None))
        .correlate(contributions)
        .scalar_subquery()
    )
    statement = select(
        contributions.c.id, contributions.c.text, contributions.c.content_hash,
        contributions.c.status.label("status"), contributions.c.received_at,
        contributions.c.reviewed_at, contributions.c.review_reason,
        current.c.category, current.c.source, automatic.c.automatic_label, automatic.c.model_version,
        flags.label("risk_signals"),
    ).select_from(contributions.outerjoin(automatic, true()).outerjoin(current, true()))
    for value, column in (
        (filters.status, contributions.c.status), (filters.category, current.c.category),
        (filters.source, current.c.source), (filters.model_version, automatic.c.model_version),
        (filters.reason, contributions.c.review_reason),
    ):
        if value is not None:
            statement = statement.where(column == value)
    for start, end, column in (
        (filters.received_from, filters.received_to, contributions.c.received_at),
        (filters.reviewed_from, filters.reviewed_to, contributions.c.reviewed_at),
    ):
        if start is not None:
            statement = statement.where(column >= start)
        if end is not None:
            statement = statement.where(column <= end)
    if filters.has_risk is not None:
        statement = statement.where(flags.is_not(None) if filters.has_risk else flags.is_(None))
    order = (contributions.c.received_at, contributions.c.id)
    return statement.order_by(*(column.desc() if filters.order == "desc" else column.asc() for column in order))
