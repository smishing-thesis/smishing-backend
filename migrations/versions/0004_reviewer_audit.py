"""Register the reviewer and decision atomically with a manual label (#13)."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint(
        "uq_labels_review_reference", "labels", ["id", "contribution_id", "origin"]
    )
    op.create_table(
        "reviews",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "contribution_id",
            sa.Uuid(),
            sa.ForeignKey("contributions.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("label_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column(
            "label_origin", sa.String(16), nullable=False, server_default="manual"
        ),
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


def downgrade():
    op.drop_table("reviews")
    op.drop_constraint("uq_labels_review_reference", "labels", type_="unique")
