import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def migrate(engine, target="head", downgrade=False):
    config = Config("alembic.ini")
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        (command.downgrade if downgrade else command.upgrade)(config, target)


@pytest.fixture
def empty_pg():
    url = os.environ.get("SMISHING_TEST_DATABASE_URL")
    if not url:
        pytest.skip(
            "Set SMISHING_TEST_DATABASE_URL for real PostgreSQL integration tests"
        )
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql" or not parsed.database.endswith(
        "_test"
    ):
        pytest.fail(
            "Integration database must be PostgreSQL with a name ending in _test"
        )
    schema = "test_" + uuid4().hex
    admin = create_engine(url, hide_parameters=True)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        url, hide_parameters=True, connect_args={"options": f"-csearch_path={schema}"}
    )
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture
def pg(empty_pg, published_metadata):
    from smishing_backend.data.model_release import parse_publication
    from smishing_backend.data.repositories.model_catalog import PostgresModelCatalog

    migrate(empty_pg)
    PostgresModelCatalog(empty_pg).register(parse_publication(*published_metadata))
    return empty_pg


@pytest.fixture
def published_metadata():
    release = {
        "tag_name": "v1.0.0",
        "html_url": "https://github.com/smishing-thesis/charcnn-smishing-model/releases/tag/v1.0.0",
        "published_at": "2026-01-02T00:00:00Z",
        "draft": False,
        "prerelease": True,
    }
    training = {
        "model_version": "1.0.0",
        "model_sha256": "a" * 64,
        "trained_at": "2026-01-01T00:00:00Z",
        "corpus_version": "synthetic-1",
        "dataset_sha256": "b" * 64,
        "dataset_path": "SYNTHETIC_PRIVATE_PATH",
        "hyperparameters": {
            "embedding_dim": 8,
            "conv_filters": 4,
            "kernel_size": 3,
            "dense_units": 4,
            "maxlen": 64,
            "optimizer": "adam",
            "loss": "binary_crossentropy",
            "epochs": 2,
            "batch_size": 4,
            "early_stopping_patience": 1,
            "early_stopping_monitor": "val_loss",
            "class_weight": "balanced",
            "val_fraction": 0.2,
            "target_fpr": 0.01,
        },
    }
    evaluation = {
        "model_version": "1.0.0",
        "model_sha256": "a" * 64,
        "threshold": 0.75,
        "validation_metrics_at_threshold": {
            "accuracy": 0.8,
            "precision": 1.0,
            "recall": 0.5,
            "f1": 0.66,
            "fpr": 0.0,
            "balanced_accuracy": 0.75,
            "tp": 1,
            "fp": 0,
            "tn": 3,
            "fn": 1,
        },
        "external_imc25_peru": {
            "n": 2,
            "detected": 1,
            "recall_at_threshold": 0.5,
            "median_score": 0.6,
        },
        "robustness_suite": [{"message": "SYNTHETIC_PRIVATE_MESSAGE"}],
    }
    return release, training, evaluation
