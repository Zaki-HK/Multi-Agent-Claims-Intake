"""Database policy metadata and strictly scoped, two-stage RAG evidence."""

from dataclasses import asdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.models.policy import Policy
from app.rag.retriever import PolicyRetriever


class PolicyRetrievalTool:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], retriever: PolicyRetriever) -> None:
        self.sessions = sessions
        self.retriever = retriever

    async def lookup(self, intake: dict) -> dict:
        number = intake.get("policy_number")
        if not number:
            return {"status": "missing_policy_number", "policy": None, "citations": []}
        async with self.sessions() as session:
            policy = await session.scalar(
                select(Policy).options(selectinload(Policy.coverages)).where(Policy.policy_number == number)
            )
            if policy is None:
                return {"status": "policy_not_found", "policy": None, "citations": []}
            metadata = {
                "id": str(policy.id), "policy_number": policy.policy_number,
                "plan_type": policy.plan_type, "status": policy.status,
                "effective_date": policy.effective_date.isoformat(),
                "expiration_date": policy.expiration_date.isoformat(),
                "coverages": [{
                    "id": str(coverage.id), "coverage_type": coverage.coverage_type,
                    "covered_services": coverage.covered_services, "exclusions": coverage.exclusions,
                    "deductible": coverage.deductible, "copay": coverage.copay,
                    "coinsurance_percent": coverage.coinsurance_percent,
                    "out_of_pocket_max": coverage.out_of_pocket_max, "annual_limit": coverage.annual_limit,
                } for coverage in policy.coverages],
            }
        incident = intake.get("incident_date")
        period_valid = None if not incident else (
            date.fromisoformat(metadata["effective_date"]) <= date.fromisoformat(incident)
            <= date.fromisoformat(metadata["expiration_date"])
        )
        query = "\n".join(str(intake.get(field) or "") for field in (
            "incident_description", "injury_type", "body_part_affected", "treatment_received",
        )).strip()
        chunks = await self.retriever.aretrieve(
            query, policy_id=metadata["id"], policy_number=number,
        ) if query else []
        return {
            "status": "retrieved" if chunks else "no_policy_evidence", "policy": metadata,
            "incident_in_policy_period": period_valid,
            "citations": [{"citation_id": chunk.point_id, **asdict(chunk)} for chunk in chunks],
        }
