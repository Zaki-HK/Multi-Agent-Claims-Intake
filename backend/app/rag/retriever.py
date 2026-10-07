"""Policy-scoped dense retrieval (top 20) followed by CPU reranking (top 5)."""

import asyncio
from dataclasses import dataclass, replace
from uuid import UUID

from qdrant_client import QdrantClient, models

from app.config import Settings, settings
from app.rag.embeddings import EmbeddingService, get_embedding_service
from app.rag.reranker import RerankerService, get_reranker_service
from app.rag.vector_store import create_qdrant_client


@dataclass(frozen=True)
class RetrievedChunk:
    point_id: str
    policy_id: str
    policy_number: str
    text: str
    page_number: int | None
    page_numbers: list[int]
    section_title: str
    source_filename: str
    vector_score: float
    rerank_score: float = 0.0


class PolicyRetriever:
    def __init__(
        self,
        config: Settings = settings,
        *,
        client: QdrantClient | None = None,
        embeddings: EmbeddingService | None = None,
        reranker: RerankerService | None = None,
    ) -> None:
        self.config = config
        self._owns_client = client is None
        self.client = client if client is not None else create_qdrant_client(config)
        self.embeddings = embeddings or (
            get_embedding_service() if config is settings else EmbeddingService(config)
        )
        self.reranker = reranker or (
            get_reranker_service() if config is settings else RerankerService(config)
        )

    def retrieve(
        self,
        query: str,
        *,
        policy_id: str | UUID | None = None,
        policy_number: str | None = None,
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        if not query.strip():
            raise ValueError("Retrieval query must not be empty")
        if policy_id is None and (policy_number is None or not policy_number.strip()):
            raise ValueError("Provide policy_id or policy_number to scope policy retrieval")
        count = self.config.rag_result_count if top_k is None else top_k
        if not 1 <= count <= self.config.rag_candidate_count:
            raise ValueError("top_k must be between 1 and RAG_CANDIDATE_COUNT")
        conditions = [models.FieldCondition(key="active", match=models.MatchValue(value=True))]
        if policy_id is not None:
            conditions.append(models.FieldCondition(
                key="policy_id", match=models.MatchValue(value=str(UUID(str(policy_id))))
            ))
        if policy_number is not None:
            if not policy_number.strip():
                raise ValueError("policy_number must not be empty")
            conditions.append(models.FieldCondition(
                key="policy_number", match=models.MatchValue(value=policy_number)
            ))
        response = self.client.query_points(
            collection_name=self.config.qdrant_policy_collection,
            query=self.embeddings.embed_query(query),
            query_filter=models.Filter(must=conditions),
            limit=self.config.rag_candidate_count,
            with_payload=True,
            with_vectors=False,
        )
        candidates = []
        for point in response.points:
            payload = point.payload or {}
            if not payload.get("text"):
                continue
            if payload.get("embedding_model") != self.config.bge_m3_model_path:
                raise ValueError("Indexed policy embedding model differs from the configured query model")
            candidates.append(RetrievedChunk(
                point_id=str(point.id), policy_id=payload["policy_id"],
                policy_number=payload["policy_number"], text=payload["text"],
                page_number=payload.get("page_number"), page_numbers=payload.get("page_numbers", []),
                section_title=payload["section_title"], source_filename=payload["source_filename"],
                vector_score=float(point.score),
            ))
        if not candidates:
            return []
        scores = self.reranker.score(query, [candidate.text for candidate in candidates])
        ranked = [replace(candidate, rerank_score=score) for candidate, score in zip(candidates, scores, strict=True)]
        return sorted(ranked, key=lambda item: (item.rerank_score, item.vector_score), reverse=True)[:count]

    async def aretrieve(
        self, query: str, *, policy_id: str | UUID | None = None,
        policy_number: str | None = None, top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        return await asyncio.to_thread(
            self.retrieve, query, policy_id=policy_id, policy_number=policy_number, top_k=top_k
        )

    def close(self) -> None:
        if self._owns_client:
            self.client.close()
