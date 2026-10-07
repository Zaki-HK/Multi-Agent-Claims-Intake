"""Claims graph with specialized agents, review interrupts, and durable state."""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import START, StateGraph
from sqlalchemy.engine import make_url

from app.agents.intake import IntakeAgent
from app.agents.decision import auto_decision, human_review
from app.agents.medical_coder import MedicalCoderAgent
from app.agents.summarizer import SummarizerAgent
from app.agents.state import ClaimProcessingState
from app.agents.supervisor import supervisor
from app.agents.triage import TriageAgent
from app.config import Settings, settings

Node = Callable[[ClaimProcessingState], Awaitable[dict]]
CHECKPOINT_SETUP_LOCK = -8_421_003_001


def build_claim_graph(
    *, checkpointer: BaseCheckpointSaver,
    duplicate_node: Node,
    policy_node: Node,
    fraud_node: Node,
    config: Settings = settings,
):
    builder = StateGraph(ClaimProcessingState)

    def route(state: ClaimProcessingState):
        return supervisor(state, config)

    builder.add_node("supervisor", route, destinations=(
        "intake", "triage", "duplicate", "policy", "medical", "fraud", "summary",
        "human_review", "decision", "__end__",
    ))
    builder.add_node("intake", IntakeAgent(config))
    builder.add_node("triage", TriageAgent(config))
    builder.add_node("duplicate", duplicate_node)
    builder.add_node("policy", policy_node)
    builder.add_node("medical", MedicalCoderAgent(config))
    builder.add_node("fraud", fraud_node)
    builder.add_node("summary", SummarizerAgent(config))
    builder.add_node("human_review", human_review)
    builder.add_node("decision", auto_decision)
    builder.add_edge(START, "supervisor")
    for node in ("intake", "triage", "duplicate", "policy", "medical", "fraud", "summary", "human_review", "decision"):
        builder.add_edge(node, "supervisor")
    # Command routes the supervisor; static outgoing edges would execute twice.
    return builder.compile(checkpointer=checkpointer)


@asynccontextmanager
async def postgres_checkpointer(config: Settings = settings) -> AsyncIterator[AsyncPostgresSaver]:
    url = make_url(config.database_url).set(drivername="postgresql").render_as_string(hide_password=False)
    async with AsyncPostgresSaver.from_conn_string(url) as saver:
        # Checkpoint tables have their own migrations. Serialize first-time setup
        # across worker processes; they are separate from application Alembic tables.
        await saver.conn.execute("SELECT pg_advisory_lock(%s)", (CHECKPOINT_SETUP_LOCK,))
        try:
            await saver.setup()
        finally:
            await saver.conn.execute("SELECT pg_advisory_unlock(%s)", (CHECKPOINT_SETUP_LOCK,))
        yield saver
