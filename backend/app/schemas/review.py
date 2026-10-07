"""Validated human decisions, queue responses, and audit history."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.claim import ClaimStatus
from app.schemas.claim import ClaimResponse


class ReviewDecisionSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reviewer_id: str = Field(min_length=1, max_length=64)
    decision: Literal["approve", "reject", "override"]
    notes: str | None = Field(default=None, max_length=5000)
    override_status: Literal["approved", "denied", "escalated"] | None = None

    @model_validator(mode="after")
    def validate_override(self) -> "ReviewDecisionSubmission":
        if self.decision == "override":
            if self.override_status is None or not self.notes:
                raise ValueError("An override requires override_status and nonblank notes")
        elif self.override_status is not None:
            raise ValueError("override_status is only valid for an override")
        if self.decision == "reject" and not self.notes:
            raise ValueError("A rejection requires nonblank notes")
        return self

    def final_status(self) -> str:
        return self.override_status if self.decision == "override" else (
            "approved" if self.decision == "approve" else "denied"
        )


class ReviewQueueItem(ClaimResponse):
    summary: str | None = None
    review_reasons: list[str] = Field(default_factory=list)


class ReviewQueueResponse(BaseModel):
    items: list[ReviewQueueItem]
    total: int
    limit: int
    offset: int


class ReviewDecisionResponse(BaseModel):
    claim_id: UUID
    review_id: UUID
    status: ClaimStatus
    decision: str
    applied: bool
    message: str


class ReviewHistoryItem(BaseModel):
    id: UUID
    reviewer_id: str
    decision: str
    notes: str | None
    created_at: datetime
    action_taken: str | None
    applied_at: datetime | None
