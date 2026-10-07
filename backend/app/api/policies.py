"""Policy repository metadata and bounded PDF ingestion using Phase 2 services."""

import asyncio
import re
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db
from app.models.policy import Policy, PolicyCoverage
from app.rag.ingest import PolicyIngestor
from app.schemas.policy import PolicyCreate, PolicyListResponse, PolicyResponse, PolicyUploadResponse
from app.services.document_service import DocumentParsingError
from app.services.policy_service import PolicyService

router = APIRouter(prefix="/policies", tags=["policies"])
Database = Annotated[AsyncSession, Depends(get_db)]


def public_policy(policy: Policy, *, indexed: bool = False) -> PolicyResponse:
    return PolicyResponse(
        **{field: getattr(policy, field) for field in (
            "id", "policy_number", "holder_name", "plan_type", "effective_date", "expiration_date", "status",
        )}, indexing_status="indexed" if indexed else "not_indexed",
    )


@router.get("", response_model=PolicyListResponse)
async def list_policies(db: Database, search: Annotated[str | None, Query(max_length=255)] = None,
                        limit: Annotated[int, Query(ge=1, le=100)] = 20,
                        offset: Annotated[int, Query(ge=0)] = 0) -> PolicyListResponse:
    criteria = []
    if search and search.strip():
        term = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        criteria.append(Policy.policy_number.ilike(f"%{term}%", escape="\\") |
                        Policy.holder_name.ilike(f"%{term}%", escape="\\"))
    total = await db.scalar(select(func.count()).select_from(Policy).where(*criteria)) or 0
    # Fetch the indexing flag without transferring complete parsed PDFs on every refresh.
    items = (await db.execute(select(
        Policy.id, Policy.policy_number, Policy.holder_name, Policy.plan_type,
        Policy.effective_date, Policy.expiration_date, Policy.status,
        (Policy.parsed_markdown.is_not(None) & (Policy.parsed_markdown != "")).label("indexed"),
    ).where(*criteria).order_by(Policy.policy_number, Policy.id).limit(limit).offset(offset))).mappings().all()
    return PolicyListResponse(items=[
        PolicyResponse(**{key: value for key, value in item.items() if key != "indexed"},
                       indexing_status="indexed" if item["indexed"] else "not_indexed")
        for item in items
    ], total=total, limit=limit, offset=offset)


@router.post("", response_model=PolicyResponse, status_code=201)
async def create_policy(request: PolicyCreate, db: Database) -> PolicyResponse:
    policy = Policy(**request.model_dump(exclude={"coverages"}))
    policy.coverages = [PolicyCoverage(**item.model_dump()) for item in request.coverages]
    db.add(policy)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A policy with that number already exists") from None
    return public_policy(policy)


@router.post("/{policy_id}/upload", response_model=PolicyUploadResponse)
async def upload_policy(policy_id: UUID, db: Database, file: Annotated[UploadFile, File()]) -> PolicyUploadResponse:
    policy = await db.get(Policy, policy_id)
    if policy is None:
        raise HTTPException(status_code=404, detail="Policy not found")
    if not file.filename or Path(file.filename).suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="Choose a PDF policy document")
    content = bytearray()
    while block := await file.read(1024 * 1024):
        content.extend(block)
        if len(content) > settings.max_upload_size_mb * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"PDF exceeds {settings.max_upload_size_mb} MB")
    if not content or b"%PDF-" not in content[:1024]:
        raise HTTPException(status_code=400, detail="File does not contain a PDF header")
    # Names and paths are generated server-side; file paths never enter public responses.
    stem = re.sub(r"[^A-Za-z0-9_.-]", "_", Path(file.filename).stem)[:140] or "policy"
    name = stem + ".pdf"
    directory = Path(settings.upload_dir).resolve() / "policies" / str(policy_id)
    destination = directory / f"{uuid4().hex}-{name}"

    def save() -> None:
        directory.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    await asyncio.to_thread(save)
    ingestor = PolicyIngestor()
    try:
        result = await PolicyService(db, ingestor).ingest_pdf(policy.policy_number, destination)
    except DocumentParsingError:
        raise HTTPException(status_code=422, detail="PDF could not be parsed completely; choose a readable policy document") from None
    except Exception:
        raise HTTPException(status_code=503, detail="Policy indexing did not complete; retry uploading when services are available") from None
    finally:
        ingestor.close()
    return PolicyUploadResponse(policy_id=policy_id, page_count=result.page_count, chunk_count=result.chunk_count)
