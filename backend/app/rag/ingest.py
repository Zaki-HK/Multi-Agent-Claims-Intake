"""PDF parsing, structural chunking, and batched policy vector ingestion."""

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4, uuid5

from qdrant_client import QdrantClient, models

from app.config import Settings, settings
from app.rag.chunking import chunk_document
from app.rag.embeddings import EmbeddingService, get_embedding_service
from app.rag.vector_store import create_qdrant_client, ensure_policy_collection
from app.services.document_service import DocumentService, get_document_service

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestionResult:
    policy_id: str
    policy_number: str
    document_path: str
    markdown: str
    page_count: int
    chunk_count: int
    ingestion_id: str


class PolicyIngestor:
    def __init__(
        self,
        config: Settings = settings,
        *,
        client: QdrantClient | None = None,
        embeddings: EmbeddingService | None = None,
        documents: DocumentService | None = None,
    ) -> None:
        self.config = config
        self._owns_client = client is None
        self.client = client if client is not None else create_qdrant_client(config)
        self.embeddings = embeddings or (
            get_embedding_service() if config is settings else EmbeddingService(config)
        )
        self.documents = documents or (
            get_document_service() if config is settings else DocumentService(config)
        )

    def ingest_pdf(self, source: str | Path, *, policy_id: str | UUID, policy_number: str) -> IngestionResult:
        policy_uuid = UUID(str(policy_id))
        if not policy_number.strip():
            raise ValueError("A policy number is required for ingestion")
        parsed = self.documents.parse_pdf(source)
        chunks = chunk_document(parsed, self.embeddings, self.config)
        collection = ensure_policy_collection(self.client, self.config)
        ingestion_id = str(uuid4())
        current_filter = models.Filter(must=[
            models.FieldCondition(key="policy_id", match=models.MatchValue(value=str(policy_uuid))),
            models.FieldCondition(key="ingestion_id", match=models.MatchValue(value=ingestion_id)),
        ])
        activated = False
        try:
            for offset in range(0, len(chunks), self.config.rag_upsert_batch_size):
                batch = chunks[offset:offset + self.config.rag_upsert_batch_size]
                vectors = self.embeddings.embed_documents([chunk.text for chunk in batch])
                points = [
                    models.PointStruct(
                        id=str(uuid5(policy_uuid, f"{ingestion_id}:{chunk.chunk_index}")),
                        vector=vector,
                        payload={
                            "policy_id": str(policy_uuid),
                            "policy_number": policy_number,
                            "ingestion_id": ingestion_id,
                            "active": False,
                            "chunk_index": chunk.chunk_index,
                            "text": chunk.text,
                            "content": chunk.content,
                            "section_title": chunk.section_title,
                            "headings": chunk.headings,
                            "page_number": chunk.page_number,
                            "page_numbers": chunk.page_numbers,
                            "source_filename": parsed.source_path.name,
                            "embedding_model": self.config.bge_m3_model_path,
                        },
                    )
                    for chunk, vector in zip(batch, vectors, strict=True)
                ]
                self.client.upsert(collection_name=collection, points=points, wait=True)
            # Publish only after every embedding batch and upsert has succeeded.
            self.client.set_payload(
                collection_name=collection,
                payload={"active": True},
                points=current_filter,
                wait=True,
            )
            activated = True
            # Remove prior revisions and abandoned staging chunks for this policy.
            self.client.delete(
                collection_name=collection,
                points_selector=models.FilterSelector(filter=models.Filter(
                    must=[models.FieldCondition(
                        key="policy_id", match=models.MatchValue(value=str(policy_uuid))
                    )],
                    must_not=[models.FieldCondition(
                        key="ingestion_id", match=models.MatchValue(value=ingestion_id)
                    )],
                )),
                wait=True,
            )
        except Exception:
            if not activated:
                try:
                    self.client.delete(
                        collection_name=collection,
                        points_selector=models.FilterSelector(filter=current_filter),
                        wait=True,
                    )
                except Exception:
                    logger.exception("Unable to clean up staged vectors for policy %s", policy_uuid)
            raise
        return IngestionResult(
            policy_id=str(policy_uuid), policy_number=policy_number,
            document_path=str(parsed.source_path), markdown=parsed.markdown,
            page_count=parsed.page_count, chunk_count=len(chunks), ingestion_id=ingestion_id,
        )

    async def aingest_pdf(self, source: str | Path, *, policy_id: str | UUID, policy_number: str) -> IngestionResult:
        return await asyncio.to_thread(
            self.ingest_pdf, source, policy_id=policy_id, policy_number=policy_number
        )

    def close(self) -> None:
        if self._owns_client:
            self.client.close()
