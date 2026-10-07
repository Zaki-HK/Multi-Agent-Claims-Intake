from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.models import (
    AuditLog, Claim, ClaimAssessment, ClaimEvent, ClaimStatus,
    HumanReview, Policy, PolicyCoverage, ReviewDecision,
)


async def test_claim_workflow_persistence(db_session):
    policy = Policy(
        policy_number="POL-TEST",
        holder_name="Test Claimant",
        plan_type="PPO",
        effective_date=date(2026, 1, 1),
        expiration_date=date(2026, 12, 31),
        coverages=[PolicyCoverage(coverage_type="outpatient")],
    )
    db_session.add(policy)
    await db_session.flush()

    claim = Claim(
        claim_number="CLM-TEST",
        raw_text="Outpatient injury treatment",
        policy_id=policy.id,
        uploaded_images=["uploads/example.png"],
    )
    db_session.add(claim)
    await db_session.flush()
    assessment = ClaimAssessment(
        claim_id=claim.id,
        intake_result={"claimant_name": "Test Claimant"},
    )
    event = ClaimEvent(claim_id=claim.id, event_type="submitted")
    review = HumanReview(
        claim_id=claim.id, reviewer_id="adjuster-1", decision="approved",
    )
    db_session.add_all([assessment, event, review])
    await db_session.flush()
    decision = ReviewDecision(review_id=review.id, action_taken="approve")
    audit = AuditLog(
        entity_type="claim", entity_id=str(claim.id), action="approved",
        changes={"status": "approved"}, actor="adjuster-1",
    )
    db_session.add_all([decision, audit])
    await db_session.commit()
    ids = {type(item): item.id for item in [
        policy, claim, assessment, event, review, decision, audit,
    ]}
    db_session.expunge_all()

    stored_claim = await db_session.get(Claim, ids[Claim])
    assert stored_claim.status is ClaimStatus.SUBMITTED
    assert stored_claim.uploaded_images == ["uploads/example.png"]
    assert stored_claim.requires_human_review is False
    assert stored_claim.created_at is not None
    assert abs((datetime.now(UTC).replace(tzinfo=None) - stored_claim.created_at).total_seconds()) < 60
    assert stored_claim.policy_id == ids[Policy]
    original_updated_at = stored_claim.updated_at
    stored_claim.status = ClaimStatus.PROCESSING
    await db_session.commit()
    assert stored_claim.updated_at > original_updated_at

    stored_assessment = await db_session.get(ClaimAssessment, ids[ClaimAssessment])
    assert stored_assessment.intake_result == {"claimant_name": "Test Claimant"}
    assert stored_assessment.triage_result == {}
    stored_policy = await db_session.scalar(
        select(Policy).where(Policy.id == ids[Policy]).options(selectinload(Policy.coverages))
    )
    assert stored_policy.coverages[0].deductible == 0.0
    assert stored_policy.coverages[0].policy is stored_policy
    for model in [ClaimEvent, HumanReview, ReviewDecision, AuditLog]:
        assert await db_session.get(model, ids[model]) is not None


async def test_database_constraints_and_rollback(db_session):
    claim = Claim(claim_number="CLM-UNIQUE", raw_text="Initial claim")
    db_session.add(claim)
    await db_session.commit()

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(Claim(claim_number="CLM-UNIQUE", raw_text="Duplicate"))
            await db_session.flush()

    db_session.add(ClaimAssessment(claim_id=claim.id))
    await db_session.commit()
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(ClaimAssessment(claim_id=claim.id))
            await db_session.flush()

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(ClaimEvent(claim_id=uuid4(), event_type="invalid_reference"))
            await db_session.flush()

    assert await db_session.get(Claim, claim.id) is claim
    db_session.add(Claim(claim_number="CLM-ROLLBACK", raw_text="Uncommitted"))
    await db_session.flush()
    await db_session.rollback()
    assert await db_session.scalar(
        select(Claim).where(Claim.claim_number == "CLM-ROLLBACK")
    ) is None
