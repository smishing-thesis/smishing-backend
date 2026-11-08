"""Operator command: register aggregate model metadata, never run inference."""

import argparse

from sqlalchemy.exc import SQLAlchemyError

from smishing_backend.config import Settings
from smishing_backend.data.connection import create_database_engine
from smishing_backend.data.model_release import read_github_publication
from smishing_backend.data.repositories.model_catalog import PostgresModelCatalog
from smishing_backend.domain.model_catalog import (
    InvalidModelPublication,
    ModelVersionConflict,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--release", required=True, help="Published model tag, e.g. v1.0.0"
    )
    args = parser.parse_args()
    engine = None
    try:
        publication = read_github_publication(args.release)
        engine = create_database_engine(Settings().database_url)
        PostgresModelCatalog(engine).register(publication)
    except (InvalidModelPublication, ModelVersionConflict, SQLAlchemyError):
        print(
            "Model metadata could not be registered; verify publication and database configuration."
        )
        return 1
    finally:
        if engine is not None:
            engine.dispose()
    print(f"Model {publication.version}: publication metadata registered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
