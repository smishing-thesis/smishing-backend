"""Operator-only export of accepted corpus rows; no public download endpoint."""

import argparse
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from smishing_backend.config import Settings
from smishing_backend.data.connection import create_database_engine
from smishing_backend.data.export_files import write_corpus
from smishing_backend.data.repositories.quarantine import PostgresQuarantineRepository
from smishing_backend.domain.corpus_export import InvalidCorpusExport, render_corpus


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    engine = None
    try:
        engine = create_database_engine(Settings().database_url)
        rows = PostgresQuarantineRepository(engine).accepted_for_training()
        artifact = render_corpus(rows)
        write_corpus(artifact, args.output_dir)
    except (SQLAlchemyError, InvalidCorpusExport, OSError, UnicodeError):
        print("Corpus export failed; check database and output configuration.")
        return 1
    finally:
        if engine is not None:
            engine.dispose()
    print(
        f"Exported {artifact.count} accepted contributions; version {artifact.version}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
