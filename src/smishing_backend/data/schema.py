"""Physical corpus tables. Domain modules do not import this metadata."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

metadata = sa.MetaData()
model_versions = sa.Table(
    "model_version",
    metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column("version_tag", sa.String(20), key="version", nullable=False, unique=True),
    sa.Column(
        "generated_at", sa.DateTime(timezone=True), key="trained_at", nullable=False
    ),
    sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("training_set", sa.String(100), key="corpus_version", nullable=False),
    sa.Column("dataset_sha256", sa.String(64), nullable=False),
    sa.Column("hyperparameters", sa.Text(), nullable=False),
    sa.Column("metrics", JSONB(), nullable=False),
    sa.Column("release_tag", sa.String(64), nullable=False),
    sa.Column("release_url", sa.String(512), nullable=False),
    sa.Column("metadata_sha256", sa.String(64), nullable=False),
    *(
        sa.Column(name, sa.Numeric(5, 4), nullable=False)
        for name in ("accuracy", "precision_score", "recall", "f1_score")
    ),
    sa.CheckConstraint(
        "accuracy BETWEEN 0 AND 1 AND precision_score BETWEEN 0 AND 1 AND recall BETWEEN 0 AND 1 AND f1_score BETWEEN 0 AND 1",
        name="ck_model_metric_ranges",
    ),
)
contributions = sa.Table(
    "contributed_message",
    metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column("text", sa.Text(), nullable=False),
    sa.Column(
        "received_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    ),
    sa.Column("content_hash", sa.CHAR(64), nullable=False),
    sa.Column(
        "review_status",
        sa.String(20),
        key="status",
        nullable=False,
        server_default="pending",
    ),
    sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("review_reason", sa.String(32), nullable=True),
    sa.CheckConstraint(
        "(review_status = 'pending' AND reviewed_at IS NULL AND review_reason IS NULL) OR (review_status IN ('accepted', 'rejected') AND reviewed_at IS NOT NULL AND review_reason IS NOT NULL AND review_reason IN ('quality_checked', 'invalid_content', 'out_of_scope'))",
        name="ck_registered_review",
    ),
    sa.CheckConstraint(
        "review_status IN ('pending', 'accepted', 'rejected')",
        name="ck_contribution_status",
    ),
    sa.CheckConstraint(
        "char_length(text) BETWEEN 1 AND 2048", name="ck_contribution_text"
    ),
    sa.CheckConstraint("content_hash ~ '^[0-9a-f]{64}$'", name="ck_contribution_hash"),
    sa.UniqueConstraint("content_hash", name="uq_contributions_content_hash"),
    sa.Index("ix_contributions_received_at", "received_at"),
)
labels = sa.Table(
    "message_label",
    metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column(
        "message_id",
        sa.Uuid(),
        sa.ForeignKey("contributed_message.id", ondelete="CASCADE"),
        key="contribution_id",
        nullable=False,
    ),
    sa.Column(
        "model_version_id", sa.Uuid(), sa.ForeignKey("model_version.id"), nullable=True
    ),
    sa.Column("category", sa.String(20), key="value", nullable=False),
    sa.Column(
        "source", sa.String(20), key="origin", nullable=False, server_default="device"
    ),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    ),
    sa.CheckConstraint(
        "(source = 'device' AND model_version_id IS NOT NULL) OR (source = 'manual' AND model_version_id IS NULL)",
        name="ck_label_provenance",
    ),
    sa.CheckConstraint("category IN ('safe', 'smishing')", name="ck_label_value"),
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
        sa.ForeignKey("contributed_message.id", ondelete="CASCADE"),
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
        ["message_label.id", "message_label.contribution_id", "message_label.origin"],
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

risk_flags = sa.Table(
    "risk_flags",
    metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column(
        "contribution_id",
        sa.Uuid(),
        sa.ForeignKey("contributed_message.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("code", sa.String(32), nullable=False),
    sa.Column(
        "raised_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    ),
    sa.Column("reviewed_at", sa.DateTime(timezone=True)),
    sa.Column("reviewer_id", sa.String(64)),
    sa.Column("review_decision", sa.String(16)),
    sa.CheckConstraint(
        "code IN ('similarity_burst', 'label_conflict', 'class_shift', 'evaluation_similarity')",
        name="ck_risk_signal",
    ),
    sa.CheckConstraint(
        "(reviewed_at IS NULL AND reviewer_id IS NULL AND review_decision IS NULL) OR (reviewed_at IS NOT NULL AND reviewer_id IS NOT NULL AND reviewer_id ~ '^[a-z0-9_-]{1,64}$' AND review_decision IS NOT NULL AND review_decision IN ('accepted', 'rejected', 'cleared'))",
        name="ck_risk_review",
    ),
    sa.Index(
        "uq_unresolved_risk",
        "contribution_id",
        "code",
        unique=True,
        postgresql_where=sa.text("reviewed_at IS NULL"),
    ),
)
