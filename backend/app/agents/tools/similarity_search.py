"""BGE-M3 similarity against previously accepted claims in Qdrant."""

import asyncio
import hashlib
import json
import logging
from uuid import UUID

from qdrant_client import QdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse

from app.config import Settings, settings
from app.rag.embeddings import EmbeddingService, get_embedding_service
from app.rag.vector_store import POLICY_VECTOR_DIMENSION, create_qdrant_client

logger = logging.getLogger(__name__)


def ensure_claim_collection(client: QdrantClient, config: Settings = settings) -> str:
    name = config.qdrant_claim_collection
    if not client.collection_exists(name):
        try:
            client.create_collection(
                collection_name=name,
                vectors_config=models.VectorParams(size=POLICY_VECTOR_DIMENSION, distance=models.Distance.COSINE),
            )
        except UnexpectedResponse as exc:
            if exc.status_code not in (400, 409) or not client.collection_exists(name):
                raise
    info = client.get_collection(name)
    vectors = info.config.params.vectors
    if (not isinstance(vectors, models.VectorParams) or vectors.size != POLICY_VECTOR_DIMENSION
            or vectors.distance != models.Distance.COSINE):
        raise ValueError(f"{name} must use unnamed 1024-dimensional cosine vectors")
    for key in ("claim_id", "policy_number", "embedding_model"):
        if key not in (info.payload_schema or {}):
            client.create_payload_index(name, key, field_schema=models.PayloadSchemaType.KEYWORD, wait=True)
    return name


class ClaimSimilaritySearch:
    def __init__(
        self, config: Settings = settings, *, client: QdrantClient | None = None,
        embeddings: EmbeddingService | None = None,
    ) -> None:
        self.config = config
        self._owns_client = client is None
        self.client = client if client is not None else create_qdrant_client(config)
        self.embeddings = embeddings or (
            get_embedding_service() if config is settings else EmbeddingService(config)
        )

    def search_and_index(
        self, *, claim_id: str, description: str, policy_number: str | None,
    ) -> dict:
        identifier = str(UUID(claim_id))
        if not description.strip():
            return {
                "status": "insufficient_data", "is_duplicate": False,
                "max_similarity_score": 0.0, "matches": [],
                "threshold": self.config.duplicate_similarity_threshold,
                "scope": "policy" if policy_number else "all_claims",
            }
        collection = ensure_claim_collection(self.client, self.config)
        signature = hashlib.sha256(json.dumps(
            [description, policy_number, self.config.bge_m3_model_path], ensure_ascii=False
        ).encode("utf-8")).hexdigest()
        existing = self.client.retrieve(collection, ids=[identifier], with_payload=True, with_vectors=False)
        if existing:
            payload = existing[0].payload or {}
            if payload.get("input_signature") == signature and payload.get("duplicate_result"):
                # A prior upsert may have succeeded before checkpoint persistence
                # failed. Keep its original search outcome when that node retries.
                return payload["duplicate_result"]
        vector = self.embeddings.embed_query(description)
        conditions = [models.FieldCondition(
            key="embedding_model", match=models.MatchValue(value=self.config.bge_m3_model_path)
        )]
        if policy_number:
            conditions.append(models.FieldCondition(
                key="policy_number", match=models.MatchValue(value=policy_number)
            ))
        response = self.client.query_points(
            collection_name=collection, query=vector,
            query_filter=models.Filter(
                must=conditions,
                must_not=[models.FieldCondition(key="claim_id", match=models.MatchValue(value=identifier))],
            ),
            limit=self.config.duplicate_candidate_count, with_payload=True, with_vectors=False,
        )
        matches = [
            {"claim_id": point.payload["claim_id"], "policy_number": point.payload.get("policy_number"),
             "similarity_score": float(point.score)}
            for point in response.points if point.payload and point.payload.get("claim_id")
        ]
        maximum = max((item["similarity_score"] for item in matches), default=0.0)
        result = {
            "status": "completed", "is_duplicate": bool(matches)
                and maximum >= self.config.duplicate_similarity_threshold,
            "max_similarity_score": maximum, "matches": matches,
            "threshold": self.config.duplicate_similarity_threshold,
            "scope": "policy" if policy_number else "all_claims",
        }
        # The same UUID is overwritten on retry, and excluded from its own search.
        self.client.upsert(collection_name=collection, points=[models.PointStruct(
            id=identifier, vector=vector,
            payload={"claim_id": identifier, "policy_number": policy_number,
                     "embedding_model": self.config.bge_m3_model_path,
                     "input_signature": signature, "duplicate_result": result},
        )], wait=True)
        return result

    async def asearch_and_index(self, *, claim_id: str, description: str, policy_number: str | None) -> dict:
        operation = asyncio.create_task(asyncio.to_thread(
            self.search_and_index, claim_id=claim_id, description=description, policy_number=policy_number
        ))
        try:
            return await asyncio.shield(operation)
        except asyncio.CancelledError:
            # A running thread cannot be cancelled. Keep the caller's duplicate
            # stage lock and client alive until its search/upsert has finished.
            try:
                await operation
            except Exception:
                logger.error("Duplicate indexing failed while cancelling claim %s", claim_id)
            raise

    def close(self) -> None:
        if self._owns_client:
            self.client.close()
