"""Physical corpus tables. Domain modules do not import this metadata."""

import sqlalchemy as sa

metadata = sa.MetaData()
model_versions = sa.Table(
    "model_versions",
    metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column("version", sa.String(64), nullable=False, unique=True),
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
    sa.CheckConstraint("value IN ('safe', 'smishing')", name="ck_label_value"),
    sa.Index("ix_labels_contribution_id", "contribution_id"),
)
