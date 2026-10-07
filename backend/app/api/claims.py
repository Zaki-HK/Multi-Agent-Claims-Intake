"""FNOL submission, workflow inspection, and processing recovery."""

import asyncio
import logging
import mimetypes
from datetime import date
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.llm import LLMOutputError, LLMUnavailableError
from app.config import settings
from app.db.session import get_db
from app.models.claim import Claim, ClaimEvent, ClaimStatus
from app.schemas.claim import (
    ClaimAssessmentResponse, ClaimDetailResponse, ClaimEventResponse,
    ClaimListResponse, ClaimResponse, EvidenceImage,
)
from app.schemas.fnol import FNOLResponse
from app.services.claim_service import (
    ClaimConflictError, ClaimNotFoundError, ClaimService, dispatch_claim,
)
from app.services.image_service import ImageService, InvalidImageError

router = APIRouter(prefix="/claims", tags=["claims"])
logger = logging.getLogger(__name__)
Database = Annotated[AsyncSession, Depends(get_db)]


async def require_claim(service: ClaimService, claim_id: UUID) -> Claim:
    try:
        return await service.get_claim(claim_id)
    except ClaimNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def evidence_images(claim: Claim) -> list[EvidenceImage]:
    return [EvidenceImage(index=index, url=f"/api/v1/claims/{claim.id}/images/{index}")
            for index in range(len(claim.uploaded_images))]


async def queue_claim(service: ClaimService, claim_id: UUID) -> None:
    try:
        await dispatch_claim(claim_id)
    except Exception:
        await service.record_failure(claim_id, error_type="TaskDispatchUnavailable", terminal=True)
        raise HTTPException(status_code=503, detail={
            "claim_id": str(claim_id),
            "message": "Claim saved. Background processing is temporarily unavailable; retry this claim shortly.",
            "retry_url": f"/api/v1/claims/{claim_id}/retry",
        }) from None


@router.post("/fnol", response_model=FNOLResponse, status_code=202)
async def submit_fnol(
    db: Database,
    description: Annotated[str, Form(min_length=1, max_length=settings.max_fnol_text_length)],
    images: Annotated[list[UploadFile] | None, File(description="JPEG, PNG, or WebP evidence")] = None,
) -> FNOLResponse:
    if not description.strip():
        raise HTTPException(status_code=422, detail="Description must not be blank")
    identifier = uuid4()
    image_service = ImageService()
    service = ClaimService(db)
    try:
        paths = await image_service.save_uploads(identifier, images or [])
        claim, intake = await service.create_fnol(identifier, description, paths)
    except Exception as exc:
        await db.rollback()
        try:
            await asyncio.to_thread(image_service.cleanup, identifier)
        except OSError:
            logger.error("Unable to remove incomplete uploads for claim %s", identifier)
        if isinstance(exc, InvalidImageError):
            raise HTTPException(status_code=400, detail=str(exc)) from None
        if isinstance(exc, LLMUnavailableError):
            raise HTTPException(status_code=503, detail="Intake model is temporarily unavailable") from None
        if isinstance(exc, LLMOutputError):
            raise HTTPException(status_code=502, detail="Intake model returned invalid structured data") from None
        raise
    # Publishing after commit means the worker can always find the saved claim.
    await queue_claim(service, identifier)
    return FNOLResponse(
        claim_id=str(claim.id), claim_number=claim.claim_number, status=claim.status.value,
        extracted_data=intake, missing_fields=intake["missing_fields"],
        message="Claim accepted for processing and specialized assessment",
    )


@router.get("", response_model=ClaimListResponse)
async def list_claims(
    db: Database, status: ClaimStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    search: Annotated[str | None, Query(max_length=255)] = None,
    date_from: date | None = None, date_to: date | None = None,
) -> ClaimListResponse:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="Start date must not follow end date")
    claims, total = await ClaimService(db).list_claims(status=status, limit=limit, offset=offset,
                                                     search=search, date_from=date_from, date_to=date_to)
    return ClaimListResponse(items=[ClaimResponse.model_validate(item) for item in claims],
                             total=total, limit=limit, offset=offset)


@router.get("/intake-settings")
async def intake_settings() -> dict:
    return {"max_images": settings.max_claim_images, "max_upload_size_mb": settings.max_upload_size_mb,
            "max_image_pixels": settings.max_image_pixels, "max_text_length": settings.max_fnol_text_length}


@router.get("/{claim_id}", response_model=ClaimDetailResponse)
async def claim_detail(claim_id: UUID, db: Database) -> ClaimDetailResponse:
    service = ClaimService(db)
    claim = await require_claim(service, claim_id)
    assessment = await service.get_assessment(claim_id)
    return ClaimDetailResponse(
        **ClaimResponse.model_validate(claim).model_dump(), raw_text=claim.raw_text,
        images=evidence_images(claim),
        assessment=ClaimAssessmentResponse.model_validate(assessment) if assessment is not None else None,
    )


@router.get("/{claim_id}/timeline", response_model=list[ClaimEventResponse])
async def claim_timeline(claim_id: UUID, db: Database):
    await require_claim(ClaimService(db), claim_id)
    return (await db.scalars(select(ClaimEvent).where(ClaimEvent.claim_id == claim_id)
                            .order_by(ClaimEvent.timestamp, ClaimEvent.id))).all()


@router.get("/{claim_id}/reasoning")
async def claim_reasoning(claim_id: UUID, db: Database) -> dict:
    service = ClaimService(db)
    await require_claim(service, claim_id)
    assessment = await service.get_assessment(claim_id)
    return {"claim_id": str(claim_id), "agents": assessment.agent_reasoning_trace if assessment else {}}


@router.get("/{claim_id}/images", response_model=list[EvidenceImage])
async def claim_images(claim_id: UUID, db: Database):
    return evidence_images(await require_claim(ClaimService(db), claim_id))


@router.get("/{claim_id}/images/{index}")
async def claim_image(claim_id: UUID, index: int, db: Database) -> FileResponse:
    claim = await require_claim(ClaimService(db), claim_id)
    if not 0 <= index < len(claim.uploaded_images):
        raise HTTPException(status_code=404, detail="Evidence image not found")
    try:
        path = ImageService().resolve_evidence(claim_id, claim.uploaded_images[index])
    except (OSError, InvalidImageError):
        raise HTTPException(status_code=404, detail="Evidence image is unavailable") from None
    return FileResponse(path, media_type=mimetypes.guess_type(path.name)[0],
                        headers={"X-Content-Type-Options": "nosniff"})


@router.post("/{claim_id}/retry", status_code=202)
async def retry_claim(claim_id: UUID, db: Database) -> dict:
    service = ClaimService(db)
    try:
        claim = await service.prepare_retry(claim_id)
    except ClaimNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ClaimConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    await queue_claim(service, claim_id)
    return {"claim_id": str(claim_id), "status": claim.status.value}
