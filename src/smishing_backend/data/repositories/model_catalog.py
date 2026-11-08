from dataclasses import asdict
from uuid import UUID, uuid4

from sqlalchemy import Engine, select, update
from sqlalchemy.dialects.postgresql import insert

from smishing_backend.data.schema import model_versions
from smishing_backend.domain.model_catalog import ModelPublication, ModelVersionConflict


class PostgresModelCatalog:
    def __init__(self, engine: Engine):
        self.engine = engine

    def register(self, publication: ModelPublication) -> UUID:
        with self.engine.begin() as connection:
            connection.execute(
                insert(model_versions)
                .values(id=uuid4(), version=publication.version)
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
            if row.metadata_sha256 is None:
                values = asdict(publication)
                values.pop("version")
                connection.execute(
                    update(model_versions)
                    .where(model_versions.c.id == row.id)
                    .values(**values)
                )
            return row.id
