from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from smishing_backend.domain.review import ReviewDecision


class ReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    decision: Literal["accepted", "rejected"]
    reason: Literal["quality_checked", "invalid_content", "out_of_scope"]
    label: Literal["safe", "smishing"]
    acknowledge_flags: bool = False

    def to_decision(self) -> ReviewDecision:
        return ReviewDecision(
            self.decision, self.reason, self.label, self.acknowledge_flags
        )


class ReviewCreated(BaseModel):
    id: UUID
    contribution_id: UUID
    reviewer_id: str
    decision: Literal["accepted", "rejected"]
    reviewed_at: datetime
    label: Literal["safe", "smishing"]
