"""Require registered reviews and terminal quarantine transitions (#12)."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

CHECK = "(status = 'pending' AND reviewed_at IS NULL AND review_reason IS NULL) OR (status IN ('accepted', 'rejected') AND reviewed_at IS NOT NULL AND review_reason IS NOT NULL AND review_reason IN ('quality_checked', 'invalid_content', 'out_of_scope'))"


def upgrade():
    op.add_column(
        "contributions",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "contributions", sa.Column("review_reason", sa.String(32), nullable=True)
    )
    # Fail safely if older installations contain terminal states with no review.
    # Never manufacture review records to make the constraint pass.
    op.create_check_constraint("ck_registered_review", "contributions", CHECK)
    op.execute("""
        CREATE FUNCTION enforce_quarantine_transition() RETURNS trigger AS $$
        BEGIN
            IF OLD.status <> 'pending' AND
               (NEW.status IS DISTINCT FROM OLD.status OR
                NEW.reviewed_at IS DISTINCT FROM OLD.reviewed_at OR
                NEW.review_reason IS DISTINCT FROM OLD.review_reason) THEN
                RAISE EXCEPTION 'Terminal review cannot be changed' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute(
        "CREATE TRIGGER quarantine_transition BEFORE UPDATE ON contributions FOR EACH ROW EXECUTE FUNCTION enforce_quarantine_transition()"
    )


def downgrade():
    op.execute("DROP TRIGGER quarantine_transition ON contributions")
    op.execute("DROP FUNCTION enforce_quarantine_transition()")
    op.drop_constraint("ck_registered_review", "contributions", type_="check")
    op.drop_column("contributions", "review_reason")
    op.drop_column("contributions", "reviewed_at")
