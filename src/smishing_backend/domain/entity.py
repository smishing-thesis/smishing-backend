"""Shared identity; event times retain their own domain meaning."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class Entity:
    id: UUID
