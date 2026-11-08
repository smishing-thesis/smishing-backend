"""Model publication facts; independent from training and inference."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


class ModelVersionConflict(Exception):
    pass


class InvalidModelPublication(Exception):
    pass


@dataclass(frozen=True)
class ModelPublication:
    version: str
    trained_at: datetime
    published_at: datetime
    corpus_version: str
    dataset_sha256: str
    hyperparameters: dict
    metrics: dict
    release_tag: str
    release_url: str
    metadata_sha256: str


class ModelCatalog(Protocol):
    def register(self, publication: ModelPublication) -> UUID: ...
