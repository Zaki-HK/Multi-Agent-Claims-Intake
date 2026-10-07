"""Accept human decisions durably before dispatching checkpoint resumes."""

from uuid import UUID, uuid5

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.claim import Claim, ClaimAssessment, ClaimEvent, ClaimStatus
from app.models.review import HumanReview, ReviewDecision
from app.schemas.claim import ClaimResponse
from app.schemas.review import ReviewDecisionSubmission, ReviewHistoryItem, ReviewQueueItem
from app.services.claim_service import ClaimConflictError, ClaimService


class ReviewService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def queue(self, *, limit: int, offset: int) -> tuple[list[ReviewQueueItem], int]:
        total = await self.session.scalar(
            select(func.count()).select_from(Claim).where(Claim.status == ClaimStatus.UNDER_REVIEW)
        ) or 0
        rows = (await self.session.execute(
            select(Claim, ClaimAssessment).outerjoin(ClaimAssessment, ClaimAssessment.claim_id == Claim.id)
            .where(Claim.status == ClaimStatus.UNDER_REVIEW).order_by(Claim.created_at, Claim.id)
            .limit(limit).offset(offset)
        )).all()
        return [ReviewQueueItem(
            **ClaimResponse.model_validate(claim).model_dump(),
            summary=assessment.summary if assessment else None,
            review_reasons=(assessment.agent_reasoning_trace or {}).get("supervisor", {}).get("review_reasons", [])
            if assessment else [],
        ) for claim, assessment in rows], total

    async def accept(self, claim_id: UUID, request: ReviewDecisionSubmission) -> tuple[Claim, HumanReview, bool]:
        key = int.from_bytes(claim_id.bytes[:8], byteorder="big", signed=True)
        if not await self.session.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": key}):
            raise ClaimConflictError("The claim is still processing; retry the decision shortly")
        claim = await ClaimService(self.session).get_claim(claim_id, lock=True)
        identifier = uuid5(claim_id, "phase4:human_review")
        review = await self.session.get(HumanReview, identifier)
        stored_decision = request.decision + (f":{request.override_status}" if request.decision == "override" else "")
        if review is not None:
            if (review.reviewer_id, review.decision, review.notes) != (request.reviewer_id, stored_decision, request.notes):
                raise ClaimConflictError("A different decision has already been accepted for this claim")
            applied = await self.session.get(ReviewDecision, uuid5(review.id, "applied")) is not None
            await self.session.commit()
            return claim, review, applied
        if claim.status != ClaimStatus.UNDER_REVIEW:
            raise ClaimConflictError("Only claims paused for human review accept a decision")
        review = HumanReview(id=identifier, claim_id=claim_id, reviewer_id=request.reviewer_id,
                             decision=stored_decision, notes=request.notes)
        self.session.add(review)
        claim.status = ClaimStatus.PROCESSING
        self.session.add_all([
            ClaimEvent(id=uuid5(identifier, "accepted_event"), claim_id=claim_id,
                       event_type="review_decision_accepted", agent_name="human_review",
                       details={"review_id": str(identifier), **request.model_dump(mode="json")}),
            AuditLog(id=uuid5(identifier, "accepted_audit"), entity_type="claim", entity_id=str(claim_id),
                     action="review_decision_accepted", actor=request.reviewer_id,
                     changes={"review_id": str(identifier), **request.model_dump(mode="json")}),
        ])
        await self.session.commit()
        return claim, review, False

    async def pending_resume(self, claim_id: UUID) -> dict | None:
        review = await self.session.get(HumanReview, uuid5(claim_id, "phase4:human_review"))
        if review is None or await self.session.get(ReviewDecision, uuid5(review.id, "applied")) is not None:
            return None
        decision, _, target = review.decision.partition(":")
        request = ReviewDecisionSubmission(reviewer_id=review.reviewer_id, decision=decision,
                                           notes=review.notes, override_status=target or None)
        return {"review_id": str(review.id), **request.model_dump(mode="json")}

    async def history(self, claim_id: UUID) -> list[ReviewHistoryItem]:
        await ClaimService(self.session).get_claim(claim_id)
        rows = (await self.session.execute(
            select(HumanReview, ReviewDecision).outerjoin(ReviewDecision, ReviewDecision.review_id == HumanReview.id)
            .where(HumanReview.claim_id == claim_id).order_by(HumanReview.created_at, HumanReview.id)
        )).all()
        return [ReviewHistoryItem(
            id=review.id, reviewer_id=review.reviewer_id, decision=review.decision,
            notes=review.notes, created_at=review.created_at,
            action_taken=applied.action_taken if applied else None,
            applied_at=applied.timestamp if applied else None,
        ) for review, applied in rows]
