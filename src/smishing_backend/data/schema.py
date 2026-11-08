"""Physical corpus tables. Domain modules do not import this metadata."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

metadata = sa.MetaData()
model_versions = sa.Table(
    "model_versions",
    metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column("version", sa.String(64), nullable=False, unique=True),
    sa.Column("trained_at", sa.DateTime(timezone=True)),
    sa.Column("published_at", sa.DateTime(timezone=True)),
    sa.Column("corpus_version", sa.String(128)),
    sa.Column("dataset_sha256", sa.String(64)),
    sa.Column("hyperparameters", JSONB()),
    sa.Column("metrics", JSONB()),
    sa.Column("release_tag", sa.String(64)),
    sa.Column("release_url", sa.String(512)),
    sa.Column("metadata_sha256", sa.String(64)),
    sa.CheckConstraint(
        "("
        + " AND ".join(
            f"{name} IS NULL"
            for name in (
                "trained_at",
                "published_at",
                "corpus_version",
                "dataset_sha256",
                "hyperparameters",
                "metrics",
                "release_tag",
                "release_url",
                "metadata_sha256",
            )
        )
        + ") OR ("
        + " AND ".join(
            f"{name} IS NOT NULL"
            for name in (
                "trained_at",
                "published_at",
                "corpus_version",
                "dataset_sha256",
                "hyperparameters",
                "metrics",
                "release_tag",
                "release_url",
                "metadata_sha256",
            )
        )
        + ")",
        name="ck_model_catalog_complete",
    ),
)
contributions = sa.Table(
    "contributions",
    metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column("text", sa.Text(), nullable=False),
    sa.Column(
        "received_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    ),
    sa.Column("content_hash", sa.String(64), nullable=False),
    sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
    sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("review_reason", sa.String(32), nullable=True),
    sa.CheckConstraint(
        "(status = 'pending' AND reviewed_at IS NULL AND review_reason IS NULL) OR (status IN ('accepted', 'rejected') AND reviewed_at IS NOT NULL AND review_reason IS NOT NULL AND review_reason IN ('quality_checked', 'invalid_content', 'out_of_scope'))",
        name="ck_registered_review",
    ),
    sa.CheckConstraint(
        "status IN ('pending', 'accepted', 'rejected')", name="ck_contribution_status"
    ),
    sa.CheckConstraint(
        "char_length(text) BETWEEN 1 AND 2048", name="ck_contribution_text"
    ),
    sa.CheckConstraint("content_hash ~ '^[0-9a-f]{64}$'", name="ck_contribution_hash"),
    sa.UniqueConstraint("content_hash", name="uq_contributions_content_hash"),
)
labels = sa.Table(
    "labels",
    metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column(
        "contribution_id",
        sa.Uuid(),
        sa.ForeignKey("contributions.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column(
        "model_version_id", sa.Uuid(), sa.ForeignKey("model_versions.id"), nullable=True
    ),
    sa.Column("value", sa.String(16), nullable=False),
    sa.Column("origin", sa.String(16), nullable=False, server_default="device"),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    ),
    sa.CheckConstraint(
        "(origin = 'device' AND model_version_id IS NOT NULL) OR (origin = 'manual' AND model_version_id IS NULL)",
        name="ck_label_provenance",
    ),
    sa.CheckConstraint("value IN ('safe', 'smishing')", name="ck_label_value"),
    sa.Index("ix_labels_contribution_id", "contribution_id"),
    sa.UniqueConstraint(
        "id", "contribution_id", "origin", name="uq_labels_review_reference"
    ),
)

reviews = sa.Table(
    "reviews",
    metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column(
        "contribution_id",
        sa.Uuid(),
        sa.ForeignKey("contributions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    ),
    sa.Column("label_id", sa.Uuid(), nullable=False, unique=True),
    sa.Column("label_origin", sa.String(16), nullable=False, server_default="manual"),
    sa.Column("reviewer_id", sa.String(64), nullable=False),
    sa.Column("decision", sa.String(16), nullable=False),
    sa.Column("reason", sa.String(32), nullable=False),
    sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(
        ["label_id", "contribution_id", "label_origin"],
        ["labels.id", "labels.contribution_id", "labels.origin"],
    ),
    sa.CheckConstraint("label_origin = 'manual'", name="ck_review_manual_label"),
    sa.CheckConstraint(
        "reviewer_id ~ '^[a-z0-9_-]{1,64}$'", name="ck_reviewer_identifier"
    ),
    sa.CheckConstraint(
        "decision IN ('accepted', 'rejected')", name="ck_review_decision"
    ),
    sa.CheckConstraint(
        "reason IN ('quality_checked', 'invalid_content', 'out_of_scope')",
        name="ck_review_reason",
    ),
)
