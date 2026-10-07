"""Claim inspection responses for intake, assessments, and review outcomes."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.claim import ClaimStatus


class ClaimResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    claim_number: str
    status: ClaimStatus
    claimant_name: str | None
    policy_number: str | None
    policy_id: UUID | None
    incident_date: date | None
    incident_description: str | None
    injury_type: str | None
    body_part_affected: str | None
    treatment_received: str | None
    provider_name: str | None
    estimated_amount: float | None
    priority: str | None
    confidence_score: float | None
    requires_human_review: bool
    created_at: datetime
    updated_at: datetime


class ClaimAssessmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    intake_result: dict
    triage_result: dict
    duplicate_check: dict
    policy_check_result: dict
    fraud_signals: dict
    medical_codes: dict
    summary: str | None
    assessment_report: str | None
    agent_reasoning_trace: dict


class EvidenceImage(BaseModel):
    index: int
    url: str


class ClaimDetailResponse(ClaimResponse):
    raw_text: str
    images: list[EvidenceImage] = Field(default_factory=list)
    assessment: ClaimAssessmentResponse | None = None


class ClaimListResponse(BaseModel):
    items: list[ClaimResponse]
    total: int
    limit: int
    offset: int


class ClaimEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    event_type: str
    agent_name: str | None
    details: dict
    timestamp: datetime
