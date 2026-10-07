"""Checkpointed claim assessment, durable review pauses, and decision resumes."""

import asyncio
import logging
from uuid import UUID

import httpx
import psycopg
from langgraph.types import Command
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse
from sqlalchemy import text
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agents.duplicate_detector import DuplicateDetectionAgent
from app.agents.graph import build_claim_graph, postgres_checkpointer
from app.agents.intake import intake_trace
from app.agents.policy_checker import PolicyCheckerAgent
from app.agents.fraud_detector import FraudDetectionAgent
from app.agents.tools.policy_retrieval import PolicyRetrievalTool
from app.agents.tools.claim_search import ClaimSearchTool
from app.agents.llm import LLMUnavailableError
from app.agents.state import initial_state
from app.celery_app import celery_app
from app.config import settings
from app.models.claim import ClaimStatus
from app.services.claim_service import ClaimService
from app.services.review_service import ReviewService
from app.rag.retriever import PolicyRetriever

logger = logging.getLogger(__name__)
DUPLICATE_STAGE_LOCK = -8_421_003_002


def is_transient(exc: Exception) -> bool:
    if isinstance(exc, UnexpectedResponse):
        return exc.status_code == 429 or exc.status_code >= 500
    return isinstance(exc, (
        LLMUnavailableError, httpx.TransportError, ResponseHandlingException,
        OperationalError, InterfaceError, psycopg.OperationalError,
    ))


async def run_claim(claim_id: UUID, *, retry_available: bool) -> dict:
    # Celery invokes asyncio.run per task. Resources belong to that loop, avoiding
    # reuse of asyncpg pools/checkpointer connections across closed event loops.
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    duplicate = None
    retriever = None
    lock_key = int.from_bytes(claim_id.bytes[:8], byteorder="big", signed=True)
    try:
        async with engine.connect() as lock_connection:
            acquired = await lock_connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_key})
            await lock_connection.commit()
            if not acquired:
                return {"claim_id": str(claim_id), "status": "already_running"}
            try:
                async with sessions() as session:
                    service = ClaimService(session)
                    claim = await service.get_claim(claim_id)
                    if claim.status != ClaimStatus.PROCESSING:
                        return {"claim_id": str(claim_id), "status": claim.status.value}
                    assessment = await service.get_assessment(claim_id)
                    intake = assessment.intake_result if assessment and assessment.intake_result else None
                    state = initial_state(str(claim_id), claim.raw_text, claim.uploaded_images, intake)
                    state["requires_human_review"] = bool(intake and intake["missing_fields"])
                    if intake:
                        state["requires_human_review"] |= intake["extraction_confidence"] < settings.human_review_confidence
                        state["agent_reasoning_trace"] = {"intake": intake_trace(intake, len(claim.uploaded_images))}
                    if assessment:
                        for field in ("triage_result", "duplicate_check", "policy_check_result", "medical_codes", "fraud_signals"):
                            result = getattr(assessment, field)
                            if result:
                                state[field] = result
                        state["summary"] = assessment.summary
                        state["assessment_report"] = assessment.assessment_report
                        state["agent_reasoning_trace"] = {
                            key: value for key, value in (assessment.agent_reasoning_trace or {}).items()
                            if key not in {"pipeline_error", "decision"}
                        }
                        if claim.confidence_score is not None:
                            state["confidence_score"] = claim.confidence_score
                        state["priority"] = claim.priority or state["priority"]
                        # Retain successful-stage flags, excluding failure-only review flags.
                        if "pipeline_error" not in (assessment.agent_reasoning_trace or {}):
                            state["requires_human_review"] = claim.requires_human_review
                    resume = await ReviewService(session).pending_resume(claim_id)
                duplicate = DuplicateDetectionAgent()
                retriever = PolicyRetriever()
                policy = PolicyCheckerAgent(PolicyRetrievalTool(sessions, retriever))
                fraud = FraudDetectionAgent(ClaimSearchTool(sessions))

                async def duplicate_node(current_state):
                    # Search and index as one serialized stage, so simultaneous
                    # reports cannot both search before either has been indexed.
                    async with engine.begin() as connection:
                        await connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": DUPLICATE_STAGE_LOCK})
                        return await duplicate(current_state)

                async with postgres_checkpointer() as checkpointer:
                    graph = build_claim_graph(checkpointer=checkpointer, duplicate_node=duplicate_node,
                                              policy_node=policy, fraud_node=fraud)
                    config = {"configurable": {"thread_id": str(claim_id)}, "recursion_limit": 40}
                    snapshot = await graph.aget_state(config)
                    if snapshot.values and snapshot.values.get("pipeline_stage") == "core_complete":
                        # The old graph ended after duplicate detection. Schedule its
                        # existing supervisor edge without repeating any core agent.
                        await graph.aupdate_state(config, {"pipeline_stage": "processing"}, as_node="duplicate")
                        snapshot = await graph.aget_state(config)
                    paused = any(task.interrupts for task in snapshot.tasks)
                    if snapshot.values and snapshot.values.get("pipeline_stage") == "completed":
                        final = snapshot.values
                    elif paused and resume is None:
                        final = snapshot.values
                    else:
                        # Resume a saved execution; never re-add reducer-backed input on retry.
                        if resume is not None:
                            if not paused:
                                raise RuntimeError("Accepted review decision has no pending checkpoint interrupt")
                            input_state = Command(resume=resume)
                        else:
                            input_state = None if snapshot.values else state
                        async for current in graph.astream(input_state, config=config, stream_mode="values"):
                            if "claim_id" in current:
                                async with sessions() as session:
                                    await ClaimService(session).persist_state(current)
                        snapshot = await graph.aget_state(config)
                        final = snapshot.values
                        paused = any(task.interrupts for task in snapshot.tasks)
                    stage = final.get("pipeline_stage")
                    if stage != "completed" and not (stage == "awaiting_review" and paused):
                        raise RuntimeError("Claim assessment did not complete or pause for review")
                    async with sessions() as session:
                        completed = await ClaimService(session).persist_state(final, finalize=True)
                    return {"claim_id": str(claim_id), "status": completed.status.value}
            except Exception as exc:
                try:
                    async with sessions() as session:
                        await ClaimService(session).record_failure(
                            claim_id, error_type=type(exc).__name__,
                            terminal=not (retry_available and is_transient(exc)),
                        )
                except Exception:
                    logger.error("Unable to persist pipeline failure for claim %s", claim_id)
                raise
            finally:
                await lock_connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key})
                await lock_connection.commit()
    finally:
        if duplicate is not None:
            duplicate.close()
        if retriever is not None:
            retriever.close()
        await engine.dispose()


@celery_app.task(bind=True, name="claims.process", max_retries=settings.claim_task_max_retries)
def process_claim(self, claim_id: str) -> dict:
    identifier = UUID(claim_id)
    retry_available = self.request.retries < settings.claim_task_max_retries
    try:
        return asyncio.run(run_claim(identifier, retry_available=retry_available))
    except Exception as exc:
        # Celery logs this sanitized exception instead of raw model/claim content.
        safe_error = RuntimeError(f"Claim pipeline failed for {identifier}: {type(exc).__name__}")
        if retry_available and is_transient(exc):
            raise self.retry(exc=safe_error, countdown=min(10 * (2 ** self.request.retries), 120)) from None
        raise safe_error from None
