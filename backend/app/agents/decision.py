"""Deterministic decision rules and a side-effect-free human review interrupt."""

from langgraph.types import interrupt

from app.agents.state import ClaimProcessingState
from app.config import Settings, settings
from app.schemas.review import ReviewDecisionSubmission


def review_reasons(state: ClaimProcessingState, config: Settings = settings) -> list[str]:
    reasons = []
    intake = state.get("intake_result") or {}
    policy = state.get("policy_check_result") or {}
    fraud = state.get("fraud_signals") or {}
    medical = state.get("medical_codes") or {}
    if intake.get("missing_fields"):
        reasons.append("Required intake fields are missing")
    if state.get("confidence_score", 0.0) < config.auto_approve_confidence:
        reasons.append("Assessment confidence is below the automatic approval threshold")
    if policy.get("eligible") is not True or policy.get("coverage_status") != "covered":
        reasons.append("Coverage eligibility needs verification")
    if policy.get("missing_information"):
        reasons.append("Policy prerequisites or supporting information are unresolved")
    if (state.get("duplicate_check") or {}).get("is_duplicate"):
        reasons.append("A possible duplicate submission needs verification")
    if medical.get("requires_review"):
        reasons.append("Medical code references or documentation need verification")
    if fraud.get("risk_score", 0.0) >= config.fraud_alert_threshold:
        reasons.append("Screening risk exceeds the investigation threshold")
    if fraud.get("status") == "insufficient_data":
        reasons.append("Policy claim history is unavailable")
    if (fraud.get("history") or {}).get("truncated"):
        reasons.append("Policy claim history exceeds the screening window limit")
    if any(item.get("evidence_id") == "future_incident_date" for item in fraud.get("screening_evidence", [])):
        reasons.append("The reported incident date is later than the submission date")
    if state.get("requires_human_review") and not reasons:
        reasons.append("An assessment stage requested human review")
    return reasons


def auto_decision(state: ClaimProcessingState) -> dict:
    return {"pipeline_stage": "completed", "current_agent": "decision",
            "requires_human_review": False,
            "final_decision": {"status": "approved", "source": "automatic",
                               "rationale": "Coverage is supported and all automatic approval criteria are satisfied."}}


def human_review(state: ClaimProcessingState) -> dict:
    # No database writes or LLM calls before interrupt: this node restarts on resume.
    response = interrupt({
        "claim_id": state["claim_id"], "review_reasons": state.get("review_reasons", []),
        "summary": state.get("summary"), "confidence_score": state.get("confidence_score"),
        "allowed_decisions": ["approve", "reject", "override"],
    })
    if not isinstance(response, dict) or "review_id" not in response:
        raise ValueError("A persisted human decision is required to resume review")
    decision = ReviewDecisionSubmission.model_validate({key: value for key, value in response.items() if key != "review_id"})
    return {
        "pipeline_stage": "completed", "current_agent": "human_review",
        "requires_human_review": False,
        "final_decision": {**decision.model_dump(mode="json"), "review_id": response["review_id"],
                           "status": decision.final_status(), "source": "human"},
    }
