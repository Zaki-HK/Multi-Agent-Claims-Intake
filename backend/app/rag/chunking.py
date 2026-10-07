"""Docling structural chunks using the same tokenizer as BGE-M3."""

from dataclasses import dataclass

from docling.chunking import HybridChunker
from docling_core.transforms.chunker.hierarchical_chunker import (
    ChunkingDocSerializer,
    ChunkingSerializerProvider,
)
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from docling_core.transforms.serializer.markdown import MarkdownTableSerializer

from app.config import Settings, settings
from app.rag.embeddings import EmbeddingService
from app.services.document_service import ParsedDocument


class PolicySerializerProvider(ChunkingSerializerProvider):
    def get_serializer(self, doc):
        return ChunkingDocSerializer(doc=doc, table_serializer=MarkdownTableSerializer())


@dataclass(frozen=True)
class PolicyChunk:
    chunk_index: int
    text: str
    content: str
    section_title: str
    headings: list[str]
    page_numbers: list[int]

    @property
    def page_number(self) -> int | None:
        return self.page_numbers[0] if self.page_numbers else None


def chunk_document(
    parsed: ParsedDocument,
    embeddings: EmbeddingService,
    config: Settings = settings,
) -> list[PolicyChunk]:
    tokenizer = HuggingFaceTokenizer(
        tokenizer=embeddings.tokenizer, max_tokens=config.rag_chunk_max_tokens
    )
    chunker = HybridChunker(
        tokenizer=tokenizer,
        merge_peers=True,
        serializer_provider=PolicySerializerProvider(),
    )
    result = []
    for chunk in chunker.chunk(dl_doc=parsed.document):
        if not chunk.text.strip():
            continue
        text = chunker.contextualize(chunk=chunk).strip()
        # Refuse oversized metadata/chunks rather than silently truncating policy clauses.
        if tokenizer.count_tokens(text) > config.rag_chunk_max_tokens:
            raise ValueError("Docling produced a chunk exceeding RAG_CHUNK_MAX_TOKENS")
        headings = list(chunk.meta.headings or [])
        pages = sorted({
            provenance.page_no
            for item in chunk.meta.doc_items
            for provenance in item.prov
        })
        result.append(PolicyChunk(
            chunk_index=len(result),
            text=text,
            content=chunk.text,
            section_title=" > ".join(headings) or "Policy terms",
            headings=headings,
            page_numbers=pages,
        ))
    if not result:
        raise ValueError("Policy document produced no searchable chunks")
    return result
