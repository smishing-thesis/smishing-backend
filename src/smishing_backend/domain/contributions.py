"""Corpus entities and persistence port, with no infrastructure imports."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID


class DuplicateContribution(Exception):
    """Content already exists, without revealing review status."""


@dataclass(frozen=True)
class Label:
    value: Literal["safe", "smishing"]
    model_version: str | None


@dataclass(frozen=True)
class NewContribution:
    text: str
    content_hash: str
    labels: tuple[Label, ...]


@dataclass(frozen=True)
class SavedContribution:
    id: UUID
    status: Literal["pending", "accepted", "rejected"]
    received_at: datetime


class ContributionRepository(Protocol):
    def save(self, contribution: NewContribution) -> SavedContribution: ...


def receive_contribution(
    contribution: NewContribution, repository: ContributionRepository
) -> SavedContribution:
    if not contribution.labels:
        raise ValueError("A contribution must have at least one label")
    return repository.save(contribution)
