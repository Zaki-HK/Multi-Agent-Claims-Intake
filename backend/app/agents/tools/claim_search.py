"""Bounded claim history for the exact policy, without unrelated narratives."""

from datetime import timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings, settings
from app.models.claim import Claim


class ClaimSearchTool:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], config: Settings = settings) -> None:
        self.sessions = sessions
        self.config = config

    async def search(self, claim_id: str, policy_number: str | None) -> dict:
        async with self.sessions() as session:
            current = await session.get(Claim, UUID(claim_id))
            if current is None:
                raise LookupError("Current claim is unavailable for history lookup")
            if not policy_number:
                return {"status": "unavailable", "total": 0, "claims": [], "truncated": False,
                        "submission_date": current.created_at.date().isoformat()}
            # Anchor the window to submission rather than retry time and exclude later claims.
            cutoff = current.created_at - timedelta(days=self.config.fraud_history_days)
            criteria = [Claim.policy_number == policy_number, Claim.id != current.id,
                        Claim.created_at >= cutoff, Claim.created_at <= current.created_at]
            total = await session.scalar(select(func.count()).select_from(Claim).where(*criteria)) or 0
            claims = (await session.scalars(
                select(Claim).where(*criteria).order_by(Claim.created_at.desc(), Claim.id)
                .limit(self.config.fraud_history_limit)
            )).all()
            return {"status": "available", "total": total, "truncated": total > len(claims),
                    "window_days": self.config.fraud_history_days,
                    "claims": [{"claim_id": str(claim.id), "status": claim.status.value,
                                "incident_date": claim.incident_date.isoformat() if claim.incident_date else None,
                                "estimated_amount": claim.estimated_amount,
                                "created_at": claim.created_at.isoformat()} for claim in claims],
                    "submission_date": current.created_at.date().isoformat()}
