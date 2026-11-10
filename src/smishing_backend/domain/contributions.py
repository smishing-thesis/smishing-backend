"""Corpus entities and persistence port, with no infrastructure imports."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from smishing_backend.domain.entity import Entity
from smishing_backend.domain.privacy import assert_anonymized


class DuplicateContribution(Exception):
    """Content already exists, without revealing review status."""


@dataclass(frozen=True)
class Label:
    value: Literal["safe", "smishing"]
    model_version: str | None
    origin: Literal["device", "manual"] = "device"


class LabelRepository(Protocol):
    def add_manual(
        self, contribution_id: UUID, value: Literal["safe", "smishing"]
    ) -> UUID: ...
    def verified(self, contribution_id: UUID) -> list[dict]: ...


@dataclass(frozen=True)
class NewContribution:
    text: str
    content_hash: str
    labels: tuple[Label, ...]


@dataclass(frozen=True)
class SavedContribution(Entity):
    status: Literal["pending"]
    received_at: datetime


class ContributionRepository(Protocol):
    def save(self, contribution: NewContribution) -> SavedContribution: ...


def receive_contribution(
    contribution: NewContribution, repository: ContributionRepository
) -> SavedContribution:
    if not contribution.labels:
        raise ValueError("A contribution must have at least one label")
    assert_anonymized(contribution.text)
    return repository.save(contribution)


class UnknownModelVersion(Exception):
    """The device version has no publication registered by an operator."""
