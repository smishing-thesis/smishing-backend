"""Align the physical corpus schema with Memoria, Figure 6 (#8)."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

SCORES = {
    "accuracy": "accuracy",
    "precision_score": "precision",
    "recall": "recall",
    "f1_score": "f1",
}
CATALOG = (
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
RENAMES = {
    "contributed_message": {"status": "review_status"},
    "message_label": {
        "contribution_id": "message_id",
        "value": "category",
        "origin": "source",
    },
    "model_version": {
        "version": "version_tag",
        "trained_at": "generated_at",
        "corpus_version": "training_set",
    },
}


def trigger(status):
    op.execute(f"""
        CREATE OR REPLACE FUNCTION enforce_quarantine_transition() RETURNS trigger AS $$
        BEGIN
            IF OLD.{status} <> 'pending' AND
               (NEW.{status} IS DISTINCT FROM OLD.{status} OR
                NEW.reviewed_at IS DISTINCT FROM OLD.reviewed_at OR
                NEW.review_reason IS DISTINCT FROM OLD.review_reason) THEN
                RAISE EXCEPTION 'Terminal review cannot be changed' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)


def upgrade():
    connection = op.get_bind()
    # Fail before changing anything. Never invent metrics or truncate old versions.
    incomplete = connection.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM model_versions WHERE "
            + " OR ".join(f"{name} IS NULL" for name in CATALOG)
            + " OR char_length(version)>20 OR char_length(corpus_version)>100)"
        )
    )
    invalid_scores = connection.scalar(
        sa.text("""
        SELECT EXISTS (
            SELECT 1 FROM model_versions m
            CROSS JOIN (VALUES ('accuracy'), ('precision'), ('recall'), ('f1')) keys(name)
            WHERE jsonb_typeof(m.metrics->'validation'->keys.name) IS DISTINCT FROM 'number'
        )
    """)
    )
    if incomplete or invalid_scores:
        raise RuntimeError(
            "Reconcile model publication metadata at revision 0004 before migration 0005; see docs/thesis-schema-review.md"
        )
    out_of_range = connection.scalar(
        sa.text("""
        SELECT EXISTS (
            SELECT 1 FROM model_versions m
            CROSS JOIN (VALUES ('accuracy'), ('precision'), ('recall'), ('f1')) keys(name)
            WHERE (m.metrics->'validation'->>keys.name)::numeric NOT BETWEEN 0 AND 1
        )
    """)
    )
    if out_of_range:
        raise RuntimeError("Reconcile model publication metrics before migration 0005")
    op.drop_constraint("ck_model_catalog_complete", "model_versions", type_="check")
    for old, new in (
        ("contributions", "contributed_message"),
        ("labels", "message_label"),
        ("model_versions", "model_version"),
    ):
        op.rename_table(old, new)
    for table, columns in RENAMES.items():
        for old, new in columns.items():
            op.alter_column(table, old, new_column_name=new)
    op.alter_column(
        "contributed_message",
        "content_hash",
        type_=sa.CHAR(64),
        existing_type=sa.String(64),
    )
    op.alter_column(
        "contributed_message",
        "review_status",
        type_=sa.String(20),
        existing_type=sa.String(16),
    )
    for name in ("category", "source"):
        op.alter_column(
            "message_label", name, type_=sa.String(20), existing_type=sa.String(16)
        )
    op.alter_column(
        "model_version", "version_tag", type_=sa.String(20), existing_type=sa.String(64)
    )
    op.alter_column(
        "model_version",
        "training_set",
        type_=sa.String(100),
        existing_type=sa.String(128),
    )
    op.alter_column(
        "model_version",
        "hyperparameters",
        type_=sa.Text(),
        existing_type=JSONB(),
        postgresql_using="hyperparameters::text",
    )
    for name in CATALOG:
        op.alter_column(
            "model_version", RENAMES["model_version"].get(name, name), nullable=False
        )
    for column, metric in SCORES.items():
        op.add_column(
            "model_version", sa.Column(column, sa.Numeric(5, 4), nullable=True)
        )
        op.execute(
            f"UPDATE model_version SET {column}=(metrics->'validation'->>'{metric}')::numeric(5,4)"
        )
        op.alter_column("model_version", column, nullable=False)
    op.create_check_constraint(
        "ck_model_metric_ranges",
        "model_version",
        " AND ".join(f"{name} BETWEEN 0 AND 1" for name in SCORES),
    )
    trigger("review_status")


def downgrade():
    trigger("status")
    op.drop_constraint("ck_model_metric_ranges", "model_version", type_="check")
    for column in SCORES:
        op.drop_column("model_version", column)
    for name in CATALOG:
        op.alter_column(
            "model_version", RENAMES["model_version"].get(name, name), nullable=True
        )
    op.alter_column(
        "model_version",
        "hyperparameters",
        type_=JSONB(),
        existing_type=sa.Text(),
        postgresql_using="hyperparameters::jsonb",
    )
    op.alter_column(
        "model_version",
        "training_set",
        type_=sa.String(128),
        existing_type=sa.String(100),
    )
    op.alter_column(
        "model_version", "version_tag", type_=sa.String(64), existing_type=sa.String(20)
    )
    for name in ("category", "source"):
        op.alter_column(
            "message_label", name, type_=sa.String(16), existing_type=sa.String(20)
        )
    op.alter_column(
        "contributed_message",
        "review_status",
        type_=sa.String(16),
        existing_type=sa.String(20),
    )
    op.alter_column(
        "contributed_message",
        "content_hash",
        type_=sa.String(64),
        existing_type=sa.CHAR(64),
    )
    for table, columns in RENAMES.items():
        for old, new in columns.items():
            op.alter_column(table, new, new_column_name=old)
    for old, new in (
        ("contributed_message", "contributions"),
        ("message_label", "labels"),
        ("model_version", "model_versions"),
    ):
        op.rename_table(old, new)
    op.create_check_constraint(
        "ck_model_catalog_complete",
        "model_versions",
        "("
        + " AND ".join(f"{name} IS NULL" for name in CATALOG)
        + ") OR ("
        + " AND ".join(f"{name} IS NOT NULL" for name in CATALOG)
        + ")",
    )
