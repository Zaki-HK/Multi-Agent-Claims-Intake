"""Shared, checkpointable state for the claims workflow."""

import operator
from typing import Annotated
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from app.schemas.fnol import FNOLData


def merge_reasoning(left: dict, right: dict) -> dict:
    return {**left, **right}


class ClaimProcessingState(TypedDict, total=False):
    raw_text: str
    image_paths: list[str]
    claim_id: str
    messages: Annotated[list[BaseMessage], add_messages]
    intake_result: FNOLData | None
    triage_result: dict | None
    policy_check_result: dict | None
    fraud_signals: dict | None
    medical_codes: dict | None
    duplicate_check: dict | None
    summary: str | None
    assessment_report: str | None
    confidence_score: float
    priority: str
    requires_human_review: bool
    current_agent: str
    pipeline_stage: str
    agent_reasoning_trace: Annotated[dict[str, dict], merge_reasoning]
    errors: Annotated[list[str], operator.add]
    review_reasons: list[str]
    final_decision: dict | None


def initial_state(
    claim_id: str, raw_text: str, image_paths: list[str], intake_result: FNOLData | None = None
) -> ClaimProcessingState:
    return {
        "claim_id": claim_id, "raw_text": raw_text, "image_paths": image_paths,
        "messages": [], "intake_result": intake_result, "triage_result": None,
        "policy_check_result": None, "fraud_signals": None, "medical_codes": None,
        "duplicate_check": None, "summary": None, "assessment_report": None,
        "confidence_score": intake_result["extraction_confidence"] if intake_result else 0.0,
        "priority": "MEDIUM", "requires_human_review": False,
        "current_agent": "supervisor", "pipeline_stage": "processing",
        "review_reasons": [], "final_decision": None,
        "agent_reasoning_trace": {}, "errors": [],
    }
