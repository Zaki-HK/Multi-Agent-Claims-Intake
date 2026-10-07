"""Qdrant client and nondestructive initialization shared by ingestion/retrieval."""

from qdrant_client import QdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse

from app.config import Settings, settings

POLICY_VECTOR_DIMENSION = 1024


def create_qdrant_client(config: Settings = settings) -> QdrantClient:
    return QdrantClient(
        url=config.qdrant_url,
        api_key=config.qdrant_api_key or None,
        timeout=config.qdrant_timeout_seconds,
    )


def ensure_policy_collection(client: QdrantClient, config: Settings = settings) -> str:
    name = config.qdrant_policy_collection
    if not client.collection_exists(name):
        try:
            client.create_collection(
                collection_name=name,
                vectors_config=models.VectorParams(
                    size=POLICY_VECTOR_DIMENSION, distance=models.Distance.COSINE
                ),
            )
        except UnexpectedResponse as exc:
            # Concurrent initializers can race to create the same collection.
            if exc.status_code not in (400, 409) or not client.collection_exists(name):
                raise
    info = client.get_collection(name)
    vectors = info.config.params.vectors
    if (
        not isinstance(vectors, models.VectorParams)
        or vectors.size != POLICY_VECTOR_DIMENSION
        or vectors.distance != models.Distance.COSINE
    ):
        raise ValueError(f"{name} must use an unnamed 1024-dimensional cosine vector")
    schema = info.payload_schema or {}
    for field in ("policy_id", "policy_number", "ingestion_id"):
        if field not in schema:
            client.create_payload_index(
                collection_name=name,
                field_name=field,
                field_schema=models.PayloadSchemaType.KEYWORD,
                wait=True,
            )
    if "active" not in schema:
        client.create_payload_index(
            collection_name=name,
            field_name="active",
            field_schema=models.PayloadSchemaType.BOOL,
            wait=True,
        )
    return name
