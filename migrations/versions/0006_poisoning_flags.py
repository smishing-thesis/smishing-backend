"""Unresolved corpus signals block training until attributed review (#14)."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "risk_flags",
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
    )
    op.create_index(
        "uq_unresolved_risk",
        "risk_flags",
        ["contribution_id", "code"],
        unique=True,
        postgresql_where=sa.text("reviewed_at IS NULL"),
    )
    op.create_index(
        "ix_contributions_received_at", "contributed_message", ["received_at"]
    )


def downgrade():
    op.drop_index("ix_contributions_received_at", table_name="contributed_message")
    op.drop_table("risk_flags")
