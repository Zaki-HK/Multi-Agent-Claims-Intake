# Phase 4: Claim assessment and human review

The implemented workflow is:

```mermaid
flowchart LR
    S[Supervisor] --> I[Intake]
    I --> S
    S --> T[Triage]
    T --> S
    S --> D[Duplicate detection]
    D --> S
    S --> P[Policy checking]
    P --> S
    S --> M[Medical coding]
    M --> S
    S --> F[Fraud screening]
    F --> S
    S --> R[Assessment report]
    R --> S
    S --> H[Human review interrupt]
    H --> S
    S --> A[Automatic approval]
    A --> S
    S --> E[Final decision]
```

The supervisor returns LangGraph `Command` objects and routes deterministically
through missing prerequisites. The shared `ClaimProcessingState` includes all
planned agent outputs, additive errors, messages using `add_messages`, and
merged agent evidence summaries. All seven assessment agents now run in
sequence. Review decisions and review reasons are checkpointed alongside the
assessments. Routing and approval thresholds are evaluated locally.

## Intake

`IntakeAgent.extract()` accepts a narrative with saved image paths or base64
image strings. Images are validated and passed to LiteLLM as image data URLs;
they do not pass through a separate OCR pipeline. JPEG, PNG, and WebP are
supported. Complete dates, reported amounts, and available attributes are
validated with Pydantic. The original text is retained and missing claimant,
policy number, incident date, and incident description are computed locally.
Unavailable attributes stay null or empty rather than being guessed.

The API runs intake before saving and queuing the claim, matching the plan's
submission flow. The graph skips an already saved intake result. Direct graph
execution without an intake result runs the intake node first.

## Triage

Triage uses `TRIAGE_MODEL` to categorize the report and provide an administrative
severity, score from 0 to 100, confidence, and a short evidence-based rationale.
Priority is normalized locally:

| Score | Priority |
| --- | --- |
| 0–24 | LOW |
| 25–49 | MEDIUM |
| 50–79 | HIGH |
| 80–100 | CRITICAL |

Severity sets a minimum score: minor 0, moderate 25, severe 50, and critical 80.
The workflow confidence is the smaller of intake and triage confidence.
Missing required intake fields or confidence below `HUMAN_REVIEW_CONFIDENCE`
mark `requires_human_review`. These scores describe extraction/triage certainty,
not coverage eligibility or approval probability.

## Duplicate detection

The duplicate agent uses Phase 2's CPU BGE-M3 service to embed the extracted
incident description. It searches `insurance_claims`, excludes the current
claim UUID, and scopes to the exact policy number when available. Without a
policy number, it searches across claims and labels that broader scope.
The default candidate count is five and threshold is `0.92` cosine similarity.

A score above the threshold sets `is_duplicate` and marks human review as
required. This flag identifies a potential repeat; it does not establish fraud
or cause a denial. Matches include claim IDs, policy numbers, and similarity
scores, without copying previous narratives into Qdrant payloads. Reports without
an incident description return `insufficient_data` and require review.

The current report is indexed after searching, using its claim UUID as the
point ID. Re-indexing overwrites that point and cannot match itself. The Celery
worker uses a PostgreSQL advisory transaction lock around search plus indexing,
so concurrent submissions cannot both search before either becomes visible.
Direct callers of the similarity tool must provide equivalent serialization.
The vector payload retains an input signature and the original duplicate
outcome. If indexing succeeds before a checkpoint write fails, retrying the same
node reuses that outcome rather than changing its result as later claims arrive.

## Background execution and checkpoints

`app.celery_app:celery_app` registers `claims.process` from `app.tasks.claims`.
Redis messages contain only the claim UUID. The worker reads the original input
and intake assessment from PostgreSQL and writes stage outputs and completion
events back after graph updates. Completion event UUIDs are deterministic to
avoid duplicate timeline entries on retry.

Each task uses a fresh asyncio event loop and its own SQLAlchemy engine and
PostgreSQL checkpointer connections. CPU embedding models remain cached within
the worker process. Per-claim advisory locks prevent duplicate deliveries from
running the same graph concurrently. Workers default to one process and one
prefetched task to limit CPU model memory usage.

`AsyncPostgresSaver` persists graph state under the claim UUID as `thread_id`.
Setup creates LangGraph's own checkpoint tables and migrations under a database
advisory lock. Alembic autogeneration excludes these externally managed tables.
Retries resume from the saved graph state, retaining already completed stages.
If the graph finished but final result persistence failed, the saved result is
reconciled without rerunning the agents.

Transient proxy, network, Qdrant server, and database connection failures are
retried up to `CLAIM_TASK_MAX_RETRIES` (default three). Backoff starts at ten
seconds. Invalid model JSON and other permanent errors escalate the claim.
Errors recorded in task logs and events contain an exception type, not raw
model responses. If PostgreSQL itself is unavailable, recording a failure must
wait for database recovery. The hard task limit defaults to 1800 seconds.

A successful workflow now automatically approves an eligible claim or pauses
at `under_review`. Processing failures set `escalated` when they can be persisted.
The retry API resumes processing failures and previously completed Phase 3
claims at `triaged`. An old `core_complete` checkpoint is advanced to its
supervisor edge, retaining its intake, triage, and duplicate outcomes.

## Policy checking

The policy tool loads the exact policy number and its coverage rows from
PostgreSQL, then invokes the Phase 2 CPU dense retriever and reranker scoped
to both policy UUID and policy number. It retains passage IDs, section titles,
pages, source filenames, text, and retrieval scores.

The model returns `covered`, `excluded`, or `uncertain` with supporting citation
IDs. Unknown citation or coverage IDs are rejected as invalid model output.
A coverage conclusion without supporting citations becomes uncertain.
`eligible=true` additionally requires an active policy and an incident date
inside its recorded term. Missing policy records, missing passages, unknown
dates, inactive policies, and out-of-term incidents require review. An excluded
or ineligible result also goes to a human reviewer rather than an automatic
denial. Cost-sharing and limits come from the selected database coverage;
unknown values remain null. The agent does not calculate a payment or assume
remaining benefits. A reported amount above the recorded annual limit is
flagged for verification.

## Medical reference matching

The medical coder runs when triage is medical or intake reports an injury, body
part, or treatment. Other claims receive `not_applicable` without an LLM call.
It matches candidates from a local, versioned ICD-10-CM/CPT catalog and allows
the model to select only those candidates. Each selection must include an exact
supporting quote from the submitted medical narrative. Unknown codes and
unsupported quotes are rejected. Outputs are documentation-based suggestions
for a reviewer, not diagnoses or billing authorization.

Set `MEDICAL_CODE_REFERENCE_PATH` to an organization-maintained UTF-8 JSON
catalog. Supply the actual reference entries and provenance in this format:

```json
{
  "version": "your-reference-release",
  "source": "your-reference-source",
  "valid_from": "2026-10-01",
  "valid_to": "2027-09-30",
  "codes": []
}
```

Each `codes` entry requires `system` (`ICD-10-CM` or `CPT`), `code`,
`description`, and optional `keywords` (a list of matching phrases). The sample
above is a structural template with no reference entries. No code catalog is
bundled or downloaded automatically. Catalog dates are checked against the
reported incident date; service-date and coding specificity still require
documentary verification. Duplicate entries and invalid code formats are
configuration errors. The file is cached per process and reloaded when its
size or modification time changes. `MEDICAL_CODE_CANDIDATE_COUNT` defaults
to 20 per code system.

An unset or missing catalog, a date outside its validity period, no matching
candidates, or ambiguous documentation marks medical coding for human review.
Mount the catalog in the worker container, for example through a Compose
override adding `./references:/app/references:ro` under `celery-worker.volumes`,
and set `MEDICAL_CODE_REFERENCE_PATH=/app/references/medical_codes.json`.
Direct graph callers need the same reference configuration. An invalid JSON
catalog escalates processing and can be retried after correcting the file.

## Fraud screening

The claim search tool reads earlier submissions on the exact policy within
`FRAUD_HISTORY_DAYS` (365 by default), anchored to the current submission date.
It excludes the current claim and later submissions, counts the full window,
and returns at most `FRAUD_HISTORY_LIMIT` rows (50 by default). Other claimants'
narratives and names are not sent to the model.

Screening evidence includes possible duplicates, repeated claims, claims with
the same incident date, and incidents dated after submission. Model flags must
reference these computed evidence IDs. Risk is a score from 0 to 1, and zero
when no supported flags are selected. A score at or above
`FRAUD_ALERT_THRESHOLD` (0.70 by default) requires review. Missing policy
history, truncated history, and a future incident date also require review.
Frequency and similarity do not establish fraud and cannot trigger denial.

## Reports and final decisions

The summarizer writes `summary` and a Markdown `assessment_report` from all
completed stage outputs. The application appends the actual cited policy
passages and their source metadata. The report describes the assessment before
a decision; finalization adds the authoritative status, decision source, and
reviewer notes. Reports and agent evidence are available in claim detail and
the reasoning endpoint.

Workflow confidence is the minimum of intake, triage, policy, applicable medical
coding, and fraud-screening confidence. Automatic approval requires confidence
at least `AUTO_APPROVE_CONFIDENCE` (0.85), supported covered eligibility, no
unresolved policy prerequisites, fraud risk below the alert threshold, and no
stage requesting review. Everything else pauses for a human decision. Thresholds
are validated in settings, with the human-review threshold no greater than the
automatic-approval threshold.

Before pausing, the supervisor stores explicit review reasons. The human review
node calls LangGraph `interrupt()` without database writes or model calls before
the pause. The worker detects the checkpoint interrupt before committing
`under_review`, so a review queue entry always has a saved graph to resume.
This follows [LangGraph's interrupt and resume contract](https://docs.langchain.com/oss/python/langgraph/interrupts).

The decision API saves a `HumanReview`, timeline event, and audit entry before
publishing the claim UUID to Celery. The worker reads this saved decision and
uses `Command(resume=...)` with the original claim thread. Approve resolves to
`approved`, reject to `denied`, and override explicitly selects `approved`,
`denied`, or `escalated`. Rejection requires notes; overrides require notes
and an explicit target status. The worker verifies the checkpoint decision
against the saved review before atomically recording the final claim status,
`ReviewDecision`, timeline event, and audit entry.

Per-claim advisory locks and deterministic record IDs prevent competing
decisions and duplicate applied records. Repeating an identical accepted
decision returns its existing result; a conflicting decision returns 409.
Broker failure retains the accepted decision and provides the claim retry URL.
Retrying resumes that decision rather than rerunning assessments. If the graph
completed before a final database write failed, the worker reconciles its saved
decision. A reviewer's intentional escalation is final and cannot be restarted
with the processing-failure retry route. Phase 4 uses the existing review,
assessment, event, and audit tables; no new application migration is required.

## Local operation

Install the updated backend dependencies and use host service addresses when
running outside Compose:

```bash
python -m pip install -e ./backend
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/insurance_agent
export QDRANT_URL=http://localhost:6333
export REDIS_URL=redis://localhost:6379/0
export CELERY_RESULT_BACKEND=redis://localhost:6379/1
export LITELLM_BASE_URL=http://localhost:4000/v1
export UPLOAD_DIR=./uploads
python scripts/setup_checkpoints.py
python scripts/setup_qdrant.py --include-claims
```

After applying the Phase 1 Alembic migrations, run the API and worker in separate
terminals with the same settings:

```bash
python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```

```bash
celery -A app.celery_app:celery_app worker --loglevel=info
```

Checkpoint and claim collection setup also run automatically when first needed.
The commands above are operational instructions; they have not been executed
as part of implementation. No Phase 4 tests or service startup commands have
been run; only static source inspection was performed.

Configure `INTAKE_MODEL` with a vision-capable model behind LiteLLM. Other core
LLM work uses `TRIAGE_MODEL`, `POLICY_MODEL`, `MEDICAL_MODEL`, `FRAUD_MODEL`, and
`SUMMARY_MODEL`. JSON object responses are requested by default;
set `LLM_JSON_MODE=prompt` for an upstream that does not support that option.
Output validation remains mandatory in either mode. Refer to `.env.example`
for image count, pixel, text, model timeout, and duplicate threshold settings.

## References

- [LangGraph graph API and Command routing](https://docs.langchain.com/oss/python/langgraph/graph-api)
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [Celery task behavior](https://docs.celeryq.dev/en/stable/userguide/tasks.html)
- [LiteLLM vision inputs](https://docs.litellm.ai/docs/completion/vision)
