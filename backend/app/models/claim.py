import enum
import uuid
from datetime import datetime, date
from sqlalchemy import String, Float, Boolean, DateTime, Date, Enum, JSON, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.models.base import Base, utc_now

class ClaimStatus(str, enum.Enum):
    SUBMITTED = "submitted"
    INTAKE = "intake"
    PROCESSING = "processing"
    TRIAGED = "triaged"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    DENIED = "denied"
    ESCALATED = "escalated"

class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    status: Mapped[ClaimStatus] = mapped_column(Enum(ClaimStatus), default=ClaimStatus.SUBMITTED)

    # Raw Submissions
    raw_text: Mapped[str] = mapped_column(Text)
    uploaded_images: Mapped[list] = mapped_column(JSON, default=list) # File paths

    # Extracted Attributes (Intake Agent)
    claimant_name: Mapped[str | None] = mapped_column(String(255))
    policy_number: Mapped[str | None] = mapped_column(String(64), index=True)
    policy_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("policies.id"))
    incident_date: Mapped[date | None] = mapped_column(Date)
    incident_description: Mapped[str | None] = mapped_column(Text)
    injury_type: Mapped[str | None] = mapped_column(String(128))
    body_part_affected: Mapped[str | None] = mapped_column(String(128))
    treatment_received: Mapped[str | None] = mapped_column(Text)
    provider_name: Mapped[str | None] = mapped_column(String(255))
    estimated_amount: Mapped[float | None] = mapped_column(Float)

    # Workflow Scoring
    priority: Mapped[str | None] = mapped_column(String(32)) # LOW, MEDIUM, HIGH, CRITICAL
    confidence_score: Mapped[float | None] = mapped_column(Float)
    requires_human_review: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

class ClaimAssessment(Base):
    __tablename__ = "claim_assessments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("claims.id"), unique=True)

    intake_result: Mapped[dict] = mapped_column(JSON, default=dict)
    triage_result: Mapped[dict] = mapped_column(JSON, default=dict)
    policy_check_result: Mapped[dict] = mapped_column(JSON, default=dict)
    fraud_signals: Mapped[dict] = mapped_column(JSON, default=dict)
    medical_codes: Mapped[dict] = mapped_column(JSON, default=dict)
    duplicate_check: Mapped[dict] = mapped_column(JSON, default=dict)
    summary: Mapped[str | None] = mapped_column(Text)
    assessment_report: Mapped[str | None] = mapped_column(Text)
    agent_reasoning_trace: Mapped[dict] = mapped_column(JSON, default=dict)

class ClaimEvent(Base):
    __tablename__ = "claim_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("claims.id"))
    event_type: Mapped[str] = mapped_column(String(64))
    agent_name: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
