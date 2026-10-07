"""FNOL persistence, specialized assessments, decisions, and task handoff."""

import asyncio
from datetime import UTC, date, datetime
from uuid import UUID, uuid4, uuid5

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.intake import IntakeAgent, intake_trace
from app.agents.state import ClaimProcessingState
from app.celery_app import celery_app
from app.config import Settings, settings
from app.models.claim import Claim, ClaimAssessment, ClaimEvent, ClaimStatus
from app.models.policy import Policy
from app.models.audit import AuditLog
from app.models.review import HumanReview, ReviewDecision
from app.schemas.fnol import FNOLData
from app.schemas.review import ReviewDecisionSubmission


class ClaimNotFoundError(LookupError):
    pass


class ClaimConflictError(ValueError):
    pass


class ClaimService:
    def __init__(self, session: AsyncSession, config: Settings = settings) -> None:
        self.session = session
        self.config = config

    async def get_claim(self, claim_id: UUID, *, lock: bool = False) -> Claim:
        query = select(Claim).where(Claim.id == claim_id)
        if lock:
            query = query.with_for_update()
        claim = await self.session.scalar(query)
        if claim is None:
            raise ClaimNotFoundError("Claim not found")
        return claim

    async def get_assessment(self, claim_id: UUID) -> ClaimAssessment | None:
        return await self.session.scalar(select(ClaimAssessment).where(ClaimAssessment.claim_id == claim_id))

    async def list_claims(self, *, status: ClaimStatus | None, limit: int, offset: int,
                          search: str | None = None, date_from: date | None = None,
                          date_to: date | None = None) -> tuple[list[Claim], int]:
        criteria = [Claim.status == status] if status is not None else []
        if search and search.strip():
            term = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            criteria.append(Claim.claim_number.ilike(f"%{term}%", escape="\\") |
                            Claim.claimant_name.ilike(f"%{term}%", escape="\\") |
                            Claim.policy_number.ilike(f"%{term}%", escape="\\"))
        if date_from:
            criteria.append(func.date(Claim.created_at) >= date_from)
        if date_to:
            criteria.append(func.date(Claim.created_at) <= date_to)
        count = await self.session.scalar(select(func.count()).select_from(Claim).where(*criteria))
        claims = (await self.session.scalars(
            select(Claim).where(*criteria).order_by(Claim.created_at.desc(), Claim.id).limit(limit).offset(offset)
        )).all()
        return list(claims), count or 0

    async def _apply_intake(self, claim: Claim, intake: FNOLData) -> None:
        for field in (
            "claimant_name", "policy_number", "incident_description", "injury_type",
            "body_part_affected", "treatment_received", "provider_name", "estimated_amount",
        ):
            setattr(claim, field, intake[field])
        claim.incident_date = date.fromisoformat(intake["incident_date"]) if intake["incident_date"] else None
        claim.policy_id = await self.session.scalar(select(Policy.id).where(Policy.policy_number == intake["policy_number"]))
        claim.confidence_score = intake["extraction_confidence"]

    async def create_fnol(self, claim_id: UUID, raw_text: str, image_paths: list[str]) -> tuple[Claim, FNOLData]:
        intake = await IntakeAgent(self.config).extract(raw_text, image_paths=image_paths)
        # Date + random suffix fit the existing 32-character column without a count race.
        number = f"CLM-{datetime.now(UTC):%Y%m%d}-{uuid4().hex[:16].upper()}"
        claim = Claim(
            id=claim_id, claim_number=number, status=ClaimStatus.PROCESSING,
            raw_text=raw_text, uploaded_images=image_paths,
            requires_human_review=bool(intake["missing_fields"])
                or intake["extraction_confidence"] < self.config.human_review_confidence,
        )
        await self._apply_intake(claim, intake)
        self.session.add(claim)
        await self.session.flush()
        self.session.add_all([
            ClaimAssessment(claim_id=claim_id, intake_result=intake,
                            agent_reasoning_trace={"intake": intake_trace(intake, len(image_paths))}),
            ClaimEvent(claim_id=claim_id, event_type="submitted", details={"image_count": len(image_paths)}),
            ClaimEvent(id=uuid5(claim_id, "phase3:intake:completed"), claim_id=claim_id,
                       event_type="agent_completed", agent_name="intake", details=intake_trace(intake, len(image_paths))),
        ])
        await self.session.commit()
        return claim, intake

    async def persist_state(self, state: ClaimProcessingState, *, finalize: bool = False) -> Claim:
        claim_id = UUID(state["claim_id"])
        claim = await self.get_claim(claim_id)
        assessment = await self.get_assessment(claim_id)
        if assessment is None:
            assessment = ClaimAssessment(claim_id=claim_id)
            self.session.add(assessment)
        if state.get("intake_result") is not None:
            await self._apply_intake(claim, state["intake_result"])
        traces = {**(assessment.agent_reasoning_trace or {}), **state.get("agent_reasoning_trace", {})}
        for node, field in (
            ("intake", "intake_result"), ("triage", "triage_result"), ("duplicate", "duplicate_check"),
            ("policy", "policy_check_result"), ("medical", "medical_codes"), ("fraud", "fraud_signals"),
        ):
            result = state.get(field)
            if result is None:
                continue
            setattr(assessment, field, result)
            phase = "phase3" if node in {"intake", "triage", "duplicate"} else "phase4"
            identifier = uuid5(claim_id, f"{phase}:{node}:completed")
            if await self.session.get(ClaimEvent, identifier) is None:
                self.session.add(ClaimEvent(
                    id=identifier, claim_id=claim_id, event_type="agent_completed",
                    agent_name=node, details=traces.get(node, result),
                ))
        if state.get("summary") is not None:
            assessment.summary = state["summary"]
        if state.get("assessment_report") is not None:
            assessment.assessment_report = state["assessment_report"]
            identifier = uuid5(claim_id, "phase4:summary:completed")
            if await self.session.get(ClaimEvent, identifier) is None:
                self.session.add(ClaimEvent(id=identifier, claim_id=claim_id, event_type="agent_completed",
                                           agent_name="summary", details=traces.get("summary", {})))
        claim.priority = state.get("priority", claim.priority)
        claim.confidence_score = state.get("confidence_score", claim.confidence_score)
        claim.requires_human_review = state.get("requires_human_review", claim.requires_human_review)
        if finalize and state.get("pipeline_stage") == "awaiting_review":
            claim.status = ClaimStatus.UNDER_REVIEW
            claim.requires_human_review = True
            traces.pop("pipeline_error", None)
            identifier = uuid5(claim_id, "phase4:review:requested")
            if await self.session.get(ClaimEvent, identifier) is None:
                self.session.add(ClaimEvent(
                    id=identifier, claim_id=claim_id, event_type="human_review_requested",
                    agent_name="supervisor", details={"review_reasons": state.get("review_reasons", [])},
                ))
        if finalize and state.get("pipeline_stage") == "completed":
            decision = state.get("final_decision")
            if not decision:
                raise ValueError("Completed processing requires a final decision")
            if decision["source"] == "human":
                review_id = UUID(decision["review_id"])
                review = await self.session.get(HumanReview, review_id)
                if review is None or review.claim_id != claim_id:
                    raise ValueError("Human decision is not persisted for this claim")
                action, _, override = review.decision.partition(":")
                accepted = ReviewDecisionSubmission(reviewer_id=review.reviewer_id, decision=action,
                                                    notes=review.notes, override_status=override or None)
                if (
                    any(decision.get(key) != value for key, value in accepted.model_dump(mode="json").items())
                    or accepted.final_status() != decision["status"]
                ):
                    raise ValueError("Checkpoint decision differs from the accepted human decision")
                applied_id = uuid5(review_id, "applied")
                if await self.session.get(ReviewDecision, applied_id) is None:
                    self.session.add(ReviewDecision(id=applied_id, review_id=review_id, action_taken=decision["status"]))
            elif decision["source"] != "automatic" or decision["status"] != "approved":
                raise ValueError("Unsupported automatic decision")
            claim.status = ClaimStatus(decision["status"])
            claim.requires_human_review = claim.status == ClaimStatus.ESCALATED
            traces.pop("pipeline_error", None)
            traces["decision"] = decision
            assessment.assessment_report = (state.get("assessment_report") or "") + (
                f"\n\n## Final decision\n\nStatus: **{decision['status']}**\n\n"
                f"Source: {decision['source']}\n\n"
                + (f"Reviewer: {decision['reviewer_id']}\n\n" if decision["source"] == "human" else "")
                + (decision.get("notes") or decision.get("rationale") or "")
            )
            identifier = uuid5(claim_id, "phase4:decision:completed")
            if await self.session.get(ClaimEvent, identifier) is None:
                self.session.add_all([
                    ClaimEvent(id=identifier, claim_id=claim_id, event_type="claim_decided",
                               agent_name="human_review" if decision["source"] == "human" else "supervisor",
                               details=decision),
                    AuditLog(id=uuid5(claim_id, "phase4:decision:audit"), entity_type="claim",
                             entity_id=str(claim_id), action="claim_decided",
                             actor=decision.get("reviewer_id", "supervisor"), changes=decision),
                ])
        assessment.agent_reasoning_trace = traces
        await self.session.commit()
        return claim

    async def record_failure(self, claim_id: UUID, *, error_type: str, terminal: bool) -> None:
        claim = await self.get_claim(claim_id, lock=True)
        if claim.status != ClaimStatus.PROCESSING:
            return
        if terminal:
            claim.status = ClaimStatus.ESCALATED
            claim.requires_human_review = True
        assessment = await self.get_assessment(claim_id)
        if assessment is not None:
            assessment.agent_reasoning_trace = {
                **(assessment.agent_reasoning_trace or {}),
                "pipeline_error": {"error_type": error_type, "retrying": not terminal},
            }
        self.session.add(ClaimEvent(
            claim_id=claim_id, event_type="pipeline_failed" if terminal else "pipeline_retrying",
            agent_name="supervisor", details={"error_type": error_type},
        ))
        await self.session.commit()

    async def prepare_retry(self, claim_id: UUID) -> Claim:
        key = int.from_bytes(claim_id.bytes[:8], byteorder="big", signed=True)
        available = await self.session.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": key})
        if not available:
            raise ClaimConflictError("The current pipeline attempt is still finishing; retry shortly")
        claim = await self.get_claim(claim_id, lock=True)
        assessment = await self.get_assessment(claim_id)
        failure = (assessment.agent_reasoning_trace or {}).get("pipeline_error") if assessment else None
        if claim.status != ClaimStatus.TRIAGED and not (claim.status == ClaimStatus.ESCALATED and failure):
            raise ClaimConflictError("Only triaged Phase 3 claims or escalated processing failures can be resumed")
        claim.status = ClaimStatus.PROCESSING
        self.session.add(ClaimEvent(claim_id=claim_id, event_type="pipeline_requested", details={"retry": True}))
        await self.session.commit()
        return claim


async def dispatch_claim(claim_id: UUID) -> None:
    # Only a UUID crosses Redis. Narrative, images, and model outputs stay in the DB/files/checkpoints.
    await asyncio.to_thread(
        celery_app.send_task, "claims.process", args=[str(claim_id)],
        task_id=str(claim_id), retry=False,
    )
