"""Persist parsed policy documents against their existing database metadata."""

import asyncio
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.policy import Policy
from app.rag.ingest import IngestionResult, PolicyIngestor

logger = logging.getLogger(__name__)


class PolicyNotFoundError(LookupError):
    pass


class PolicyService:
    def __init__(self, session: AsyncSession, ingestor: PolicyIngestor) -> None:
        self.session = session
        self.ingestor = ingestor

    async def ingest_pdf(self, policy_number: str, source: str | Path) -> IngestionResult:
        # Cancellation cannot stop the underlying worker thread. Finish the current
        # document before releasing its database lock or closing the Qdrant client.
        task = asyncio.create_task(self._ingest_pdf(policy_number, source))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            try:
                await task
            except Exception:
                logger.exception("Current policy ingestion failed while awaiting cancellation")
            raise

    async def _ingest_pdf(self, policy_number: str, source: str | Path) -> IngestionResult:
        try:
            # Serialize updates to the same policy across CLI runs and future API calls.
            policy = await self.session.scalar(
                select(Policy).where(Policy.policy_number == policy_number).with_for_update()
            )
            if policy is None:
                raise PolicyNotFoundError(f"No policy metadata exists for {policy_number!r}")
            result = await self.ingestor.aingest_pdf(
                source, policy_id=policy.id, policy_number=policy.policy_number
            )
            policy.document_path = result.document_path
            policy.parsed_markdown = result.markdown
            await self.session.commit()
            return result
        except BaseException:
            await self.session.rollback()
            raise
