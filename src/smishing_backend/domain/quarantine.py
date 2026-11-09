"""Internal review port. No reviewer/device identity or public review API."""

from typing import Literal, Protocol
from uuid import UUID

Decision = Literal["accepted", "rejected"]
Reason = Literal["quality_checked", "invalid_content", "out_of_scope"]


class InvalidTransition(Exception):
    pass


class QuarantineRepository(Protocol):
    def review(
        self, contribution_id: UUID, decision: Decision, reason: Reason
    ) -> None: ...
    def accepted_for_training(self) -> list[dict]: ...


def register_review(
    contribution_id: UUID,
    decision: Decision,
    reason: Reason,
    repository: QuarantineRepository,
) -> None:
    if decision not in {"accepted", "rejected"} or reason not in {
        "quality_checked",
        "invalid_content",
        "out_of_scope",
    }:
        raise InvalidTransition()
    repository.review(contribution_id, decision, reason)
