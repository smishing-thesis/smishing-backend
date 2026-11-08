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
def pg(empty_pg):
    migrate(empty_pg)
    return empty_pg
