from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal

from pydantic import Field, model_validator

class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@postgres:5432/insurance_agent"

    # Qdrant
    qdrant_url: str = "http://qdrant:6333"
    qdrant_api_key: str | None = None
    qdrant_policy_collection: str = "insurance_policies"
    qdrant_claim_collection: str = "insurance_claims"
    qdrant_timeout_seconds: float = Field(default=60.0, gt=0)

    # LiteLLM Proxy
    litellm_base_url: str = "http://litellm:4000/v1"
    litellm_api_key: str = "sk-local-dev-key"
    llm_timeout_seconds: float = Field(default=120.0, gt=0)
    llm_max_output_tokens: int = Field(default=4096, ge=256)
    llm_json_mode: Literal["json_object", "prompt"] = "json_object"

    # LLM Model Assignments (configurable per agent)
    supervisor_model: str = "claims-model"
    intake_model: str = "claims-model"
    triage_model: str = "claims-model"
    policy_model: str = "claims-model"
    fraud_model: str = "claims-model"
    medical_model: str = "claims-model"
    summary_model: str = "claims-model"
    duplicate_model: str = "claims-model"

    # Embeddings & Reranking (CPU)
    bge_m3_model_path: str = "BAAI/bge-m3"
    bge_reranker_model_path: str = "BAAI/bge-reranker-v2-m3"
    embedding_device: Literal["cpu"] = "cpu"
    embedding_batch_size: int = Field(default=8, ge=1)
    embedding_max_length: int = Field(default=8192, ge=32, le=8192)
    reranker_batch_size: int = Field(default=8, ge=1)
    reranker_max_length: int = Field(default=1024, ge=32, le=8192)
    rag_chunk_max_tokens: int = Field(default=512, ge=32, le=8190)
    rag_upsert_batch_size: int = Field(default=32, ge=1)
    rag_candidate_count: int = Field(default=20, ge=1)
    rag_result_count: int = Field(default=5, ge=1)
    docling_num_threads: int = Field(default=4, ge=1)
    docling_max_pages: int = Field(default=500, ge=1)
    docling_enable_ocr: bool = True

    # Decision Thresholds
    auto_approve_confidence: float = Field(default=0.85, ge=0, le=1)
    human_review_confidence: float = Field(default=0.60, ge=0, le=1)
    fraud_alert_threshold: float = Field(default=0.70, gt=0, le=1)
    medical_code_reference_path: str | None = None
    medical_code_candidate_count: int = Field(default=20, ge=1, le=100)
    fraud_history_days: int = Field(default=365, ge=1, le=3650)
    fraud_history_limit: int = Field(default=50, ge=1, le=200)

    # Redis Broker
    redis_url: str = "redis://redis:6379/0"
    celery_result_backend: str | None = None
    claim_task_max_retries: int = Field(default=3, ge=0)
    claim_task_timeout_seconds: int = Field(default=1800, ge=60)
    duplicate_similarity_threshold: float = Field(default=0.92, ge=0, le=1)
    duplicate_candidate_count: int = Field(default=5, ge=1, le=50)

    # File Upload Configuration
    max_upload_size_mb: int = Field(default=25, ge=1)
    upload_dir: str = "/app/uploads"
    max_claim_images: int = Field(default=10, ge=1, le=50)
    max_image_pixels: int = Field(default=40_000_000, ge=1)
    max_fnol_text_length: int = Field(default=20_000, ge=1)

    @model_validator(mode="after")
    def validate_rag_limits(self) -> "Settings":
        if self.medical_code_reference_path is not None and not self.medical_code_reference_path.strip():
            self.medical_code_reference_path = None
        if self.human_review_confidence > self.auto_approve_confidence:
            raise ValueError("HUMAN_REVIEW_CONFIDENCE cannot exceed AUTO_APPROVE_CONFIDENCE")
        if self.rag_chunk_max_tokens + 2 > self.embedding_max_length:
            raise ValueError("RAG chunks must fit the embedding context, including special tokens")
        if self.rag_chunk_max_tokens + 4 >= self.reranker_max_length:
            raise ValueError("Reranker context must leave room for a query alongside the chunk")
        if self.rag_result_count > self.rag_candidate_count:
            raise ValueError("RAG_RESULT_COUNT cannot exceed RAG_CANDIDATE_COUNT")
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
