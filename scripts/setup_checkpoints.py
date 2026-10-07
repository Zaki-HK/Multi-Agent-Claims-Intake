"""Create or migrate LangGraph checkpoint tables without running a claim."""

import asyncio
import logging

from app.agents.graph import postgres_checkpointer


async def setup() -> None:
    async with postgres_checkpointer():
        logging.info("LangGraph PostgreSQL checkpoint tables are ready")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    asyncio.run(setup())
