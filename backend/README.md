# Insurance Agent backend

## Claim assessment pipeline (Phase 4)

Multimodal intake, triage, duplicate detection, LangGraph PostgreSQL checkpoints,
Celery tasks, and FNOL submission/inspection routes are implemented alongside
policy RAG assessment, medical reference matching, fraud screening, Markdown
reports, and human review interrupts. See [the agent guide](../docs/agents.md)
and [API guide](../docs/api.md) for review decisions and recovery. New claims
are approved automatically when all criteria pass or paused at `under_review`.
Existing Phase 3 `triaged` claims can resume through the retry route.
Set `MEDICAL_CODE_REFERENCE_PATH` to a versioned local ICD-10-CM/CPT JSON catalog;
medical claims without an applicable reference require human review.
Phase 4 reuses the existing tables and needs no additional migration.
No Phase 4 tests or runtime setup commands have been run.

## Dashboard support (Phase 5)

Policy metadata creation/listing, PDF ingestion, dashboard analytics, intake
limits, and claim search/date filters are implemented for the Vue dashboard.
See [the API guide](../docs/api.md) and [frontend guide](../docs/frontend.md).
These routes reuse the existing tables and Phase 2 ingestion services; no
additional migration is required. Static syntax checks passed; no tests ran.

## Policy RAG pipeline (Phase 2)

Docling PDF parsing, CPU BGE-M3 embeddings, CPU BGE reranking, policy-scoped
retrieval, and batch ingestion are implemented. See [the RAG guide](../docs/rag.md)
for dependency installation, collection initialization, PDF-to-policy mappings,
and retrieval usage. No Phase 2 tests have been run yet.

## Local database setup

From the repository root, start PostgreSQL with `docker compose up -d postgres`.
Compose requires a local `.env`; copy `.env.example` to `.env` if needed.

Activate the project environment and install the backend:

```bash
source ~/anaconda3/bin/activate
conda activate llmDev
python -m pip install -e './backend[test]'
```

The example database URL uses the Docker service hostname `postgres`. When
running Python on the host, use `localhost` instead:

```bash
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/insurance_agent
python -m alembic -c backend/alembic.ini upgrade head
python -m alembic -c backend/alembic.ini current
python -m alembic -c backend/alembic.ini check
```

The initial migration creates policies, policy coverages, claims, assessments,
events, human reviews, review decisions, and audit logs. Migration files own
schema creation; application startup does not call `create_all()`.

From `backend/`, create future migrations with
`python -m alembic revision --autogenerate -m "describe change"` and review the
generated revision before running `python -m alembic upgrade head`.

## Database verification

Tests require a separate PostgreSQL database already migrated to `head`.
Set `TEST_DATABASE_URL` to its `postgresql+asyncpg://...` URL, then run
`python -m pytest backend/tests/test_db -v`. Without that variable, database
tests skip. Each test uses a transaction that rolls back its writes.
