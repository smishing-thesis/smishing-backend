import json
from dataclasses import asdict
from uuid import UUID, uuid4

from sqlalchemy import Engine, MetaData, Table, select, text, update
from sqlalchemy.dialects.postgresql import insert

from smishing_backend.data.schema import model_versions
from smishing_backend.domain.model_catalog import (
    InvalidModelPublication,
    ModelPublication,
    ModelVersionConflict,
)


class PostgresModelCatalog:
    def __init__(self, engine: Engine):
        self.engine = engine

    def register(self, publication: ModelPublication) -> UUID:
        values = asdict(publication)
        values["hyperparameters"] = json.dumps(
            values["hyperparameters"],
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        scores = publication.metrics["validation"]
        values.update(
            accuracy=scores["accuracy"],
            precision_score=scores["precision"],
            recall=scores["recall"],
            f1_score=scores["f1"],
        )
        with self.engine.begin() as connection:
            connection.execute(
                insert(model_versions)
                .values(id=uuid4(), **values)
                .on_conflict_do_nothing(index_elements=[model_versions.c.version])
            )
            row = connection.execute(
                select(model_versions)
                .where(model_versions.c.version == publication.version)
                .with_for_update()
            ).one()
            if (
                row.metadata_sha256 is not None
                and row.metadata_sha256 != publication.metadata_sha256
            ):
                raise ModelVersionConflict(
                    "A different publication is already registered for this version"
                )
            return row.id


class LegacyModelCatalog:
    """Explicit operator bridge before the strict physical-schema migration."""

    def __init__(self, engine: Engine):
        self.engine = engine

    def register(self, publication: ModelPublication) -> UUID:
        with self.engine.begin() as connection:
            if (
                connection.scalar(text("SELECT version_num FROM alembic_version"))
                != "0004"
            ):
                raise InvalidModelPublication("Preparation requires revision 0004")
            table = Table("model_versions", MetaData(), autoload_with=connection)
            values = asdict(publication)
            connection.execute(
                insert(table)
                .values(id=uuid4(), **values)
                .on_conflict_do_nothing(index_elements=[table.c.version])
            )
            row = connection.execute(
                select(table)
                .where(table.c.version == publication.version)
                .with_for_update()
            ).one()
            if row.metadata_sha256 is None:
                values.pop("version")
                connection.execute(
                    update(table).where(table.c.id == row.id).values(**values)
                )
            elif row.metadata_sha256 != publication.metadata_sha256:
                raise ModelVersionConflict(
                    "A different publication is already registered"
                )
            return row.id
