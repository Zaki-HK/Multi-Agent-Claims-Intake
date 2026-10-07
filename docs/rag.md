# Phase 2: Policy document ingestion and retrieval

Policy PDFs are converted with Docling into Markdown, then chunked using the
BGE-M3 tokenizer and Docling's document structure. Section headings and original
PDF page references accompany each chunk. Tables use Markdown serialization.
The full Markdown and source path are saved on the existing PostgreSQL `Policy`
record after successful indexing.

BGE-M3 produces 1024-dimensional dense vectors on CPU. The
`insurance_policies` collection uses cosine distance. Retrieval requires a
policy ID or policy number, searches 20 active chunks, and returns the five
highest scoring chunks after BGE-Reranker-v2-M3 reranking on CPU. Results include
both similarity and reranker relevance scores plus citation metadata. Relevance
scores are not claim approval probabilities.

## Install and configure

From the repository root, install the backend in your Python 3.11+ environment:

```bash
python -m pip install -e ./backend
```

Install a CPU build of PyTorch first if you want to avoid downloading CUDA
packages; follow the [PyTorch installation instructions](https://pytorch.org/get-started/locally/).
Both BGE services explicitly use CPU and full precision regardless of the
installed PyTorch build. Docling also uses CPU. Its built-in OCR can process
scanned policy PDFs; no external Tesseract installation is required by this
configuration. FNOL image intake belongs to Phase 3.

Start the existing PostgreSQL and Qdrant services and apply the Phase 1
migrations before ingestion. Commands in this guide run from the repository
root after installing the backend. When running Python on the host, use:

```bash
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/insurance_agent
export QDRANT_URL=http://localhost:6333
```

In Compose, retain the `postgres` and `qdrant` service hostnames. Configuration
is loaded from environment variables and the current directory's `.env`.
New Phase 2 settings are listed in `.env.example`; existing `.env` files can
omit them to use the defaults.

| Setting | Default | Purpose |
| --- | --- | --- |
| `BGE_M3_MODEL_PATH` | `BAAI/bge-m3` | Hub model ID or local model directory |
| `BGE_RERANKER_MODEL_PATH` | `BAAI/bge-reranker-v2-m3` | Hub model ID or local model directory |
| `EMBEDDING_DEVICE` | `cpu` | CPU is the only accepted device |
| `EMBEDDING_BATCH_SIZE` | `8` | CPU embedding batch size |
| `EMBEDDING_MAX_LENGTH` | `8192` | Embedding context including special tokens |
| `RERANKER_BATCH_SIZE` | `8` | CPU reranking batch size |
| `RERANKER_MAX_LENGTH` | `1024` | Combined query and passage context |
| `RAG_CHUNK_MAX_TOKENS` | `512` | Chunk size including heading context |
| `RAG_UPSERT_BATCH_SIZE` | `32` | Points sent in each Qdrant upsert |
| `RAG_CANDIDATE_COUNT` | `20` | Vector candidates before reranking |
| `RAG_RESULT_COUNT` | `5` | Results after reranking |
| `QDRANT_POLICY_COLLECTION` | `insurance_policies` | Collection name |
| `QDRANT_API_KEY` | empty | Optional Qdrant authentication |
| `QDRANT_TIMEOUT_SECONDS` | `60` | Client request timeout |
| `DOCLING_NUM_THREADS` | `4` | PDF conversion CPU threads |
| `DOCLING_MAX_PAGES` | `500` | Maximum pages per policy PDF |
| `DOCLING_ENABLE_OCR` | `true` | OCR for scanned policy content |
| `MAX_UPLOAD_SIZE_MB` | `25` | Maximum PDF size |

Parsing rejects invalid, empty, oversized, failed, and partially converted PDFs
before indexing. Settings reject inconsistent chunk/context and retrieval limits.

Models load lazily. Importing the services or running the collection initializer
does not download model weights. The first ingestion downloads the Docling and
BGE-M3 models if absent; the first retrieval also loads the reranker. Provide
network access and a persistent model cache for these initial downloads.

Optional explicit BGE downloads using the Hugging Face CLI:

```bash
hf download BAAI/bge-m3 --local-dir ./models/bge-m3
hf download BAAI/bge-reranker-v2-m3 --local-dir ./models/bge-reranker-v2-m3
export BGE_M3_MODEL_PATH=./models/bge-m3
export BGE_RERANKER_MODEL_PATH=./models/bge-reranker-v2-m3
```

Docling has its own parsing/OCR model downloads. Prefetching the BGE models
alone does not make PDF conversion offline. Keep downloaded weights outside
version control and use consistent BGE paths for ingestion and retrieval.

## Initialize Qdrant

```bash
python scripts/setup_qdrant.py --qdrant-url http://localhost:6333
```

The initializer creates the collection and payload indexes for `policy_id`,
`policy_number`, `ingestion_id`, and `active`. It can be rerun. It preserves
existing points and rejects incompatible vector dimensions or distance metrics.
Ingestion also initializes the collection if needed.

## Ingest policies

Create policy metadata in PostgreSQL first. Ingestion looks up the exact policy
number and uses its database UUID; it does not infer holder names, coverage,
or effective dates from filenames. Policy CRUD APIs are not implemented in
this phase. For an illustrative local metadata record, execute this SQL in
PostgreSQL and replace the example values with the actual policy information:

```sql
INSERT INTO policies
    (id, policy_number, holder_name, plan_type, effective_date, expiration_date, status)
VALUES
    (gen_random_uuid(), 'POL-001', 'Example Holder', 'PPO', '2026-01-01', '2026-12-31', 'active');
```

Index a single PDF against that record:

```bash
python scripts/ingest_pdfs.py ./policies/coverage.pdf --policy-number POL-001
```

Index a directory recursively, using each filename stem as its policy number
(for example, `POL-001.pdf` maps to `POL-001`):

```bash
python scripts/ingest_pdfs.py ./policies
```

For arbitrary filenames, supply a JSON manifest. Paths are relative to the
source directory, and only the listed PDFs are ingested:

```json
{
  "employee-cover.pdf": "POL-001",
  "renewals/family-cover.pdf": "POL-002"
}
```

```bash
python scripts/ingest_pdfs.py ./policies --manifest ./policy_manifest.json
```

Each policy maps to one authoritative PDF. Duplicate policy mappings and missing
manifest files are rejected before ingestion. Unknown database policy numbers
are reported as failures. Batch processing continues after a document failure;
use `--fail-fast` to stop immediately. The script logs page/chunk counts and a
batch summary and exits nonzero if any document failed. `--database-url` and
`--qdrant-url` can override the corresponding environment settings.
Interrupting the CLI waits for the current document to finish before releasing
its database lock and connections; it does not start another document.

New chunks are staged as inactive. They become searchable after every upsert
batch succeeds, then older chunks for that policy are removed. Failed staging
is cleaned up without replacing the old index. PostgreSQL row locks serialize
ingestion for the same policy when called through `PolicyService`, as the CLI
does. Direct `PolicyIngestor` callers must supply equivalent serialization.

PostgreSQL and Qdrant do not share a transaction. Publishing and removing old
vectors are separate operations: retrieval during that brief interval can see
both revisions. If publication succeeds but pruning or the subsequent database
commit fails, rerun ingestion to reconcile the index and Markdown. A successful
rerun leaves one active revision per policy, including when the new PDF has
fewer chunks. Source PDFs must remain at the stored path for later access.

## Use the retriever in later agents

```python
from app.rag.retriever import PolicyRetriever

retriever = PolicyRetriever()
try:
    chunks = await retriever.aretrieve(
        "What exclusions and deductible apply to emergency treatment?",
        policy_number="POL-001",
    )
    for chunk in chunks:
        # Include this metadata when citing policy evidence in the agent output.
        print(chunk.section_title, chunk.page_numbers, chunk.text)
finally:
    retriever.close()
```

Synchronous `retrieve()` is also available. CPU inference and blocking Qdrant
requests in the async interface run in a worker thread. Empty matching policy
results return an empty list; infrastructure and model failures propagate to
the caller. The collection must already be initialized.

## Library references

- [Docling conversion](https://docling-project.github.io/docling/usage/)
- [Docling hybrid chunking](https://docling-project.github.io/docling/_generated/examples/hybrid_chunking/)
- [BGE-M3](https://bge-model.com/tutorial/1_Embedding/1.2.4.html)
- [BGE rerankers](https://bge-model.com/tutorial/5_Reranking/5.2.html)
- [Qdrant collections](https://qdrant.tech/documentation/manage-data/collections/)
