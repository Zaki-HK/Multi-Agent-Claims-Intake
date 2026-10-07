"""BGE-Reranker-v2-M3 relevance scoring, loaded only on first use."""

import asyncio
import math
from collections.abc import Sequence
from functools import lru_cache
from numbers import Real
from threading import Lock

from app.config import Settings, settings


class RerankerService:
    def __init__(self, config: Settings = settings) -> None:
        self.config = config
        self._model = None
        self._lock = Lock()

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        if not query.strip():
            raise ValueError("Reranking query must not be empty")
        if not passages:
            return []
        if any(not passage.strip() for passage in passages):
            raise ValueError("Reranking passages must not be empty")
        with self._lock:
            if self._model is None:
                from FlagEmbedding import FlagReranker

                self._model = FlagReranker(
                    self.config.bge_reranker_model_path, devices=["cpu"], use_fp16=False
                )
            raw_scores = self._model.compute_score(
                [[query, passage] for passage in passages],
                batch_size=self.config.reranker_batch_size,
                max_length=self.config.reranker_max_length,
                query_max_length=self.config.reranker_max_length - self.config.rag_chunk_max_tokens - 4,
                normalize=True,
            )
        scores = [float(raw_scores)] if isinstance(raw_scores, Real) else [float(s) for s in raw_scores]
        if len(scores) != len(passages) or any(
            not math.isfinite(score) or not 0 <= score <= 1 for score in scores
        ):
            raise RuntimeError("BGE reranker returned invalid relevance scores")
        return scores

    async def ascore(self, query: str, passages: Sequence[str]) -> list[float]:
        return await asyncio.to_thread(self.score, query, passages)


@lru_cache(maxsize=1)
def get_reranker_service() -> RerankerService:
    return RerankerService()
