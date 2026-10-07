"""Lazy, serialized BGE-M3 inference on CPU in full precision."""

import asyncio
import math
from collections.abc import Sequence
from functools import lru_cache
from threading import RLock

from app.config import Settings, settings


class EmbeddingService:
    dimension = 1024

    def __init__(self, config: Settings = settings) -> None:
        self.config = config
        self._model = None
        self._lock = RLock()

    def _get_model(self):
        if self._model is None:
            from FlagEmbedding import BGEM3FlagModel

            self._model = BGEM3FlagModel(
                self.config.bge_m3_model_path,
                devices=["cpu"],
                use_fp16=False,
                normalize_embeddings=True,
            )
        return self._model

    @property
    def tokenizer(self):
        with self._lock:
            return self._get_model().tokenizer

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError("Embedding inputs must be nonempty strings")
        with self._lock:
            output = self._get_model().encode(
                list(texts),
                batch_size=self.config.embedding_batch_size,
                max_length=self.config.embedding_max_length,
                return_dense=True,
                return_sparse=False,
                return_colbert_vecs=False,
            )
            vectors = output["dense_vecs"].tolist()
        if len(vectors) != len(texts):
            raise RuntimeError("BGE-M3 returned an unexpected number of embeddings")
        if any(
            len(vector) != self.dimension or not all(math.isfinite(value) for value in vector)
            for vector in vectors
        ):
            raise RuntimeError("BGE-M3 must return finite 1024-dimensional embeddings")
        return vectors

    def embed_query(self, query: str) -> list[float]:
        return self.embed_documents([query])[0]

    async def aembed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return await asyncio.to_thread(self.embed_documents, texts)

    async def aembed_query(self, query: str) -> list[float]:
        return await asyncio.to_thread(self.embed_query, query)


@lru_cache(maxsize=1)
def get_embedding_service() -> EmbeddingService:
    return EmbeddingService()
