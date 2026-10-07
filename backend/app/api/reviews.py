"""Human review queue, durable decisions, and checkpoint-resume dispatch."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.claims import queue_claim
from app.db.session import get_db
from app.models.claim import ClaimStatus
from app.schemas.review import (
    ReviewDecisionResponse, ReviewDecisionSubmission, ReviewHistoryItem, ReviewQueueResponse,
)
from app.services.claim_service import ClaimConflictError, ClaimNotFoundError, ClaimService
from app.services.review_service import ReviewService

router = APIRouter(prefix="/reviews", tags=["reviews"])
Database = Annotated[AsyncSession, Depends(get_db)]


@router.get("/queue", response_model=ReviewQueueResponse)
async def review_queue(db: Database, limit: Annotated[int, Query(ge=1, le=100)] = 20,
                       offset: Annotated[int, Query(ge=0)] = 0) -> ReviewQueueResponse:
    items, total = await ReviewService(db).queue(limit=limit, offset=offset)
    return ReviewQueueResponse(items=items, total=total, limit=limit, offset=offset)


@router.post("/{claim_id}/decision", response_model=ReviewDecisionResponse, status_code=202)
async def submit_decision(claim_id: UUID, request: ReviewDecisionSubmission, db: Database) -> ReviewDecisionResponse:
    try:
        claim, review, applied = await ReviewService(db).accept(claim_id, request)
    except ClaimNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ClaimConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    if not applied and claim.status == ClaimStatus.PROCESSING:
        await queue_claim(ClaimService(db), claim_id)
    return ReviewDecisionResponse(
        claim_id=claim.id, review_id=review.id, status=claim.status, decision=review.decision,
        applied=applied, message="Decision already applied" if applied else (
            "Decision saved; resume queued" if claim.status == ClaimStatus.PROCESSING else
            "Decision saved; retry this escalated claim to resume processing"
        ),
    )


@router.get("/{claim_id}/history", response_model=list[ReviewHistoryItem])
async def review_history(claim_id: UUID, db: Database) -> list[ReviewHistoryItem]:
    try:
        return await ReviewService(db).history(claim_id)
    except ClaimNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
