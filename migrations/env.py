"""Use environment configuration; never interpolate credentials into ini files."""

from alembic import context
from sqlalchemy import create_engine

from smishing_backend.config import Settings
from smishing_backend.data.schema import metadata


def run(connection):
    context.configure(connection=connection, target_metadata=metadata)
    with context.begin_transaction():
        context.run_migrations()


supplied = context.config.attributes.get("connection")
if supplied is not None:
    run(supplied)
else:
    engine = create_engine(Settings().database_url, hide_parameters=True)
    if engine.dialect.name != "postgresql":
        raise RuntimeError("PostgreSQL is required for migrations")
    with engine.connect() as connection:
        run(connection)
    engine.dispose()
