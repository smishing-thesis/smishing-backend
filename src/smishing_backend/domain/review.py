from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from smishing_backend.domain.entity import Entity
from smishing_backend.domain.quarantine import Decision, Reason


@dataclass(frozen=True)
class ReviewDecision:
    decision: Decision
    reason: Reason
    label: Literal["safe", "smishing"]
    acknowledge_flags: bool = False


@dataclass(frozen=True)
class RegisteredReview(Entity):
    contribution_id: UUID
    reviewer_id: str
    decision: Decision
    reviewed_at: datetime
    label: Literal["safe", "smishing"]


class ReviewRepository(Protocol):
    def pending(self, limit: int) -> list[dict]: ...
    def decide(
        self, contribution_id: UUID, reviewer_id: str, decision: ReviewDecision
    ) -> RegisteredReview: ...
    def flagged(self, limit: int) -> list[dict]: ...
    def acknowledge(self, contribution_id: UUID, reviewer_id: str) -> int: ...
