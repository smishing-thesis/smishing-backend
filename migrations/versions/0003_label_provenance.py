"""Label provenance and publication-backed model catalog (#15)."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

CATALOG_COLUMNS = (
    ("trained_at", sa.DateTime(timezone=True)),
    ("published_at", sa.DateTime(timezone=True)),
    ("corpus_version", sa.String(128)),
    ("dataset_sha256", sa.String(64)),
    ("hyperparameters", JSONB()),
    ("metrics", JSONB()),
    ("release_tag", sa.String(64)),
    ("release_url", sa.String(512)),
    ("metadata_sha256", sa.String(64)),
)
CATALOG_CHECK = (
    "("
    + " AND ".join(f"{name} IS NULL" for name, _ in CATALOG_COLUMNS)
    + ") OR ("
    + " AND ".join(f"{name} IS NOT NULL" for name, _ in CATALOG_COLUMNS)
    + ")"
)


def upgrade():
    # A missing model reference does not prove that a legacy label was reviewed.
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM labels WHERE model_version_id IS NULL) THEN
                RAISE EXCEPTION 'Reconcile legacy label provenance before migration 0003';
            END IF;
        END $$
    """)
    op.add_column("labels", sa.Column("origin", sa.String(16), nullable=True))
    op.execute("UPDATE labels SET origin = 'device'")
    op.alter_column("labels", "origin", nullable=False, server_default="device")
    op.add_column(
        "labels",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_check_constraint(
        "ck_label_provenance",
        "labels",
        "(origin = 'device' AND model_version_id IS NOT NULL) OR (origin = 'manual' AND model_version_id IS NULL)",
    )
    for name, type_ in CATALOG_COLUMNS:
        op.add_column("model_versions", sa.Column(name, type_, nullable=True))
    op.create_check_constraint(
        "ck_model_catalog_complete", "model_versions", CATALOG_CHECK
    )


def downgrade():
    op.drop_constraint("ck_model_catalog_complete", "model_versions", type_="check")
    for name, _ in reversed(CATALOG_COLUMNS):
        op.drop_column("model_versions", name)
    op.drop_constraint("ck_label_provenance", "labels", type_="check")
    op.drop_column("labels", "created_at")
    op.drop_column("labels", "origin")
