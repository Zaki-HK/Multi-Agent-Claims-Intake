"""Dashboard aggregates from persisted claims, decisions, and event timestamps."""

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.base import utc_now
from app.models.claim import Claim, ClaimAssessment, ClaimEvent, ClaimStatus
from app.models.policy import Policy
from app.models.review import HumanReview
from app.schemas.claim import ClaimResponse


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def summary(self) -> dict:
        rows = (await self.session.execute(select(Claim.status, func.count()).group_by(Claim.status))).all()
        counts = {status.value: 0 for status in ClaimStatus}
        counts.update({status.value: count for status, count in rows})
        auto = await self.session.scalar(
            select(func.count()).select_from(Claim).join(ClaimAssessment, ClaimAssessment.claim_id == Claim.id)
            .where(Claim.status == ClaimStatus.APPROVED,
                   ClaimAssessment.agent_reasoning_trace["decision"]["source"].as_string() == "automatic")
        ) or 0
        fraud = await self.session.scalar(
            select(func.count()).select_from(ClaimAssessment)
            .where(ClaimAssessment.fraud_signals["risk_score"].as_float() >= settings.fraud_alert_threshold)
        ) or 0
        reviews = await self.session.scalar(select(func.count()).select_from(HumanReview)) or 0
        overrides = await self.session.scalar(select(func.count()).select_from(HumanReview)
                                             .where(HumanReview.decision.like("override:%"))) or 0
        duration = await self.session.scalar(
            select(func.avg(func.extract("epoch", ClaimEvent.timestamp - Claim.created_at)))
            .select_from(ClaimEvent).join(Claim, Claim.id == ClaimEvent.claim_id)
            .where(ClaimEvent.event_type == "claim_decided")
        )
        policies = await self.session.scalar(select(func.count()).select_from(Policy)) or 0
        indexed = await self.session.scalar(select(func.count()).select_from(Policy)
                                           .where(Policy.parsed_markdown.is_not(None), Policy.parsed_markdown != "")) or 0
        claims = (await self.session.scalars(select(Claim).order_by(Claim.created_at.desc(), Claim.id).limit(5))).all()
        events = (await self.session.execute(
            select(ClaimEvent, Claim.claim_number).join(Claim, Claim.id == ClaimEvent.claim_id)
            .order_by(ClaimEvent.timestamp.desc(), ClaimEvent.id).limit(8)
        )).all()
        return {
            "total_claims": sum(counts.values()), "under_review": counts["under_review"],
            "auto_approved": auto, "fraud_flagged": fraud,
            "processing": counts["submitted"] + counts["intake"] + counts["processing"],
            "by_status": counts, "human_decisions": reviews, "overrides": overrides,
            "override_rate": overrides / reviews if reviews else None,
            "average_completion_seconds": float(duration) if duration is not None else None,
            "total_policies": policies, "indexed_policies": indexed,
            "recent_claims": [ClaimResponse.model_validate(claim).model_dump(mode="json") for claim in claims],
            "recent_events": [{"id": str(event.id), "claim_id": str(event.claim_id),
                               "claim_number": number, "event_type": event.event_type,
                               "agent_name": event.agent_name, "timestamp": event.timestamp.isoformat()}
                              for event, number in events],
        }

    async def trends(self, days: int) -> dict:
        today = utc_now().date()
        start = today - timedelta(days=days - 1)
        submitted = dict((await self.session.execute(
            select(func.date(Claim.created_at), func.count()).where(func.date(Claim.created_at) >= start,
                                                                  func.date(Claim.created_at) <= today)
            .group_by(func.date(Claim.created_at))
        )).all())
        completed = (await self.session.execute(
            select(func.date(ClaimEvent.timestamp), func.count(),
                   func.avg(func.extract("epoch", ClaimEvent.timestamp - Claim.created_at)))
            .select_from(ClaimEvent).join(Claim, Claim.id == ClaimEvent.claim_id)
            .where(ClaimEvent.event_type == "claim_decided", func.date(ClaimEvent.timestamp) >= start,
                   func.date(ClaimEvent.timestamp) <= today).group_by(func.date(ClaimEvent.timestamp))
        )).all()
        decisions = {day: (count, float(duration) if duration is not None else None) for day, count, duration in completed}
        reviews = dict((await self.session.execute(
            select(func.date(HumanReview.created_at), func.count()).where(func.date(HumanReview.created_at) >= start,
                                                                        func.date(HumanReview.created_at) <= today)
            .group_by(func.date(HumanReview.created_at))
        )).all())
        overrides = dict((await self.session.execute(
            select(func.date(HumanReview.created_at), func.count()).where(
                func.date(HumanReview.created_at) >= start, func.date(HumanReview.created_at) <= today,
                HumanReview.decision.like("override:%"))
            .group_by(func.date(HumanReview.created_at))
        )).all())
        points = []
        for offset in range(days):
            day = start + timedelta(days=offset)
            decided, duration = decisions.get(day, (0, None))
            points.append({"date": day.isoformat(), "submitted": submitted.get(day, 0), "decided": decided,
                           "human_decisions": reviews.get(day, 0), "overrides": overrides.get(day, 0),
                           "average_completion_seconds": duration})
        return {"days": days, "timezone": "UTC", "points": points}
