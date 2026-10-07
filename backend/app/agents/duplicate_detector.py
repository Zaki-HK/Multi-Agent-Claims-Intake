"""Flag potentially repeated incident reports; similarity is not a decision."""

from app.agents.state import ClaimProcessingState
from app.agents.tools.similarity_search import ClaimSimilaritySearch
from app.config import Settings, settings


class DuplicateDetectionAgent:
    def __init__(self, config: Settings = settings, *, search: ClaimSimilaritySearch | None = None) -> None:
        self.search = search or ClaimSimilaritySearch(config)
        self._owns_search = search is None

    async def __call__(self, state: ClaimProcessingState) -> dict:
        intake = state.get("intake_result")
        if intake is None:
            raise ValueError("Intake must complete before duplicate detection")
        result = await self.search.asearch_and_index(
            claim_id=state["claim_id"], description=intake["incident_description"],
            policy_number=intake["policy_number"],
        )
        return {
            "duplicate_check": result, "current_agent": "duplicate",
            "requires_human_review": state.get("requires_human_review", False)
                or result["is_duplicate"] or result["status"] != "completed",
            "agent_reasoning_trace": {"duplicate": {
                **result,
                "rationale": "Similarity identifies potential repeats requiring verification; it does not prove duplication.",
            }},
        }

    def close(self) -> None:
        if self._owns_search:
            self.search.close()
