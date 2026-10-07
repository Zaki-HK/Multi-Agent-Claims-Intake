"""Route prerequisites, specialized assessments, and final review decisions."""

from typing import Literal

from langgraph.graph import END
from langgraph.types import Command

from app.agents.decision import review_reasons
from app.agents.state import ClaimProcessingState
from app.config import Settings, settings


def supervisor(state: ClaimProcessingState, config: Settings = settings) -> Command[Literal[
    "intake", "triage", "duplicate", "policy", "medical", "fraud", "summary",
    "human_review", "decision", "__end__",
]]:
    if state.get("errors"):
        return Command(update={"current_agent": "supervisor", "pipeline_stage": "failed",
                               "requires_human_review": True}, goto=END)
    if state.get("final_decision"):
        return Command(update={"pipeline_stage": "completed"}, goto=END)
    for node, output in (
        ("intake", "intake_result"), ("triage", "triage_result"), ("duplicate", "duplicate_check"),
        ("policy", "policy_check_result"), ("medical", "medical_codes"),
        ("fraud", "fraud_signals"), ("summary", "assessment_report"),
    ):
        if state.get(output) is None:
            return Command(update={"current_agent": node, "pipeline_stage": "processing"}, goto=node)
    reasons = review_reasons(state, config)
    return Command(update={
        "current_agent": "human_review" if reasons else "decision",
        "pipeline_stage": "awaiting_review" if reasons else "assessed",
        "requires_human_review": bool(reasons), "review_reasons": reasons,
        "agent_reasoning_trace": {"supervisor": {
            "review_reasons": reasons, "auto_approve_threshold": config.auto_approve_confidence,
            "fraud_alert_threshold": config.fraud_alert_threshold,
            "confidence_score": state.get("confidence_score", 0.0),
        }},
    }, goto="human_review" if reasons else "decision")
