# Phase 5 workspace API

Base path: `/api/v1`. The Vue dashboard uses claims, human review, policy
management, and analytics routes. Progress uses polling; WebSocket updates
remain in later work. Interactive API documentation is available at `/docs`.

| Method | Path | Response |
| --- | --- | --- |
| POST | `/claims/fnol` | 202: extracted FNOL and claim ID; assessment pipeline queued |
| GET | `/claims` | Paginated claims; optional `status`, `search`, `date_from`, `date_to`, `limit`, `offset` |
| GET | `/claims/intake-settings` | Configured image, text, and upload limits |
| GET | `/claims/{claim_id}` | Extracted fields, original text, evidence URLs, and assessment |
| GET | `/claims/{claim_id}/timeline` | Chronological persisted agent and workflow events |
| GET | `/claims/{claim_id}/reasoning` | Agent evidence summaries and recorded errors |
| GET | `/claims/{claim_id}/images` | Evidence image indexes and URLs |
| GET | `/claims/{claim_id}/images/{index}` | Original validated evidence image |
| POST | `/claims/{claim_id}/retry` | 202: resume a processing failure or an existing Phase 3 triaged claim |
| GET | `/reviews/queue` | Paginated claims paused for review, with summary and reasons |
| POST | `/reviews/{claim_id}/decision` | 202: persist a human decision and queue checkpoint resume |
| GET | `/reviews/{claim_id}/history` | Accepted decisions and their applied outcomes |
| GET | `/policies` | Paginated policy metadata, document indexing flag; optional `search`, `limit`, `offset` |
| POST | `/policies` | 201: create policy metadata with optional coverage rows |
| POST | `/policies/{policy_id}/upload` | 200: parse PDF and index passages; multipart `file` |
| GET | `/analytics/summary` | Current status totals, all-time metrics, recent claims and events |
| GET | `/analytics/trends` | Daily UTC activity; optional `days` from 7 to 90, default 30 |

Claims search matches claim number, claimant name, and policy number using
case-insensitive literal substring matching. Date filters select submission
dates in UTC, including both bounds; a reversed range returns 422. Policy
search matches policy number and policyholder. Listing limits are 1–100;
offsets must be nonnegative. The frontend uses server pagination.

## Submit an FNOL

Send `multipart/form-data` with a nonblank `description`. Repeat the `images`
field for attached JPEG, PNG, or WebP files. Images are optional; for an
image-led submission, include context in the description.

```bash
curl -X POST http://localhost:8000/api/v1/claims/fnol \
  -F 'description=Incident narrative, including any known claimant and policy details.' \
  -F 'images=@./evidence/damage.jpg'
```

The default limits are 20,000 narrative characters, ten images, 25 MB combined
image content, and 40 million pixels per image. Animated images are rejected.
File contents are validated and generated filenames are used for storage.
Evidence URLs only resolve files recorded for that claim inside its upload
directory; filesystem paths are not returned in the public claim response.

Intake runs first through LiteLLM. Once extraction succeeds, the claim and
assessment are committed, then Redis receives a Celery task containing only
the claim ID. A successful request returns:

```json
{
  "claim_id": "<uuid>",
  "claim_number": "CLM-<date>-<random suffix>",
  "status": "processing",
  "extracted_data": {},
  "missing_fields": [],
  "message": "Claim accepted for processing and specialized assessment"
}
```

The actual `extracted_data` includes normalized intake fields, the original
narrative, extraction confidence, and missing fields. Poll claim detail or
timeline for background progress. New claims proceed through policy checking,
medical coding, fraud screening, and report generation after the core agents.
They finish at `approved` when all automatic criteria pass, or `under_review`
with a saved graph interrupt. Processing failures become `escalated`.
Claim detail includes all agent outputs, the summary, and the Markdown report.

## Failures and recovery

Invalid images return 400; invalid form fields return 422. An unavailable
intake model returns 503; malformed model output returns 502. These intake
failures do not persist a claim, and newly saved evidence files are removed.

If Redis dispatch fails after the claim is committed, the API returns 503 with
the saved `claim_id` and `retry_url`. Evidence and extraction are retained,
and the claim is escalated. Retry that ID when the broker is available:

```bash
curl -X POST http://localhost:8000/api/v1/claims/<claim_id>/retry
```

Retries preserve the existing claim and resume completed graph stages. The
endpoint also accepts old Phase 3 claims at `triaged`; their core assessments
are retained while specialized agents run. It returns 409 for other statuses,
intentional reviewer escalations, or a claim whose current attempt still holds
the processing lock. It returns 404 for unknown IDs. Pipeline errors
and retry events are available in the timeline; agent outputs and flags are
available in claim detail and `/reasoning`.

## Review a claim

`GET /api/v1/reviews/queue?limit=20&offset=0` returns `items`, `total`, `limit`,
and `offset`. Each item includes public claim fields, the assessment `summary`,
and `review_reasons`. Only claims at `under_review` appear in the queue.
Use claim detail to inspect full evidence and the report before deciding.

Submit a JSON decision using one of `approve`, `reject`, or `override`:

```bash
curl -X POST http://localhost:8000/api/v1/reviews/<claim_id>/decision \
  -H 'Content-Type: application/json' \
  -d '{"reviewer_id":"adjuster-123","decision":"approve","notes":"Verified policy terms and supporting evidence."}'
```

Approval resolves to `approved`; rejection resolves to `denied` and requires
nonblank notes. An override requires notes and an explicit `override_status`
of `approved`, `denied`, or `escalated`, for example:

```json
{
  "reviewer_id": "adjuster-123",
  "decision": "override",
  "override_status": "escalated",
  "notes": "Refer to the specialist investigation team."
}
```

The API records the review before queueing the worker and returns:

```json
{
  "claim_id": "<uuid>",
  "review_id": "<uuid>",
  "status": "processing",
  "decision": "approve",
  "applied": false,
  "message": "Decision saved; resume queued"
}
```

Poll claim detail for the applied status. `/reviews/{claim_id}/history` shows
the accepted reviewer, decision, notes, acceptance time, `action_taken`, and
`applied_at`; the last two remain null until finalization. Override decisions
are recorded as `override:<target-status>`. Timeline and reasoning expose the
final decision source as well as the earlier assessment evidence.

An identical repeat request returns the existing accepted decision. A conflicting
decision, a claim still processing, or a claim that is not paused for review
returns 409. Unknown claims return 404. Invalid decisions, missing rejection
notes, or incomplete overrides return 422. If dispatch fails, the accepted
decision is retained and the 503 response supplies `/claims/{claim_id}/retry`.
That retry resumes the saved decision without repeating assessment stages.
A decision already applied is returned with `applied=true` and is not queued again.

The Phase 1 authentication scope is unchanged: `reviewer_id` is a caller-supplied
audit identifier, not an authenticated identity.

Medical reference configuration and automatic approval criteria are documented
in [the agent guide](agents.md). Without an applicable configured ICD-10-CM/CPT
catalog, medical claims require human coding review.

## Policy metadata and PDFs

Create the policy record before uploading its PDF:

```bash
curl -X POST http://localhost:8000/api/v1/policies \
  -H 'Content-Type: application/json' \
  -d '{"policy_number":"POL-001","holder_name":"Example Policyholder","plan_type":"PPO","effective_date":"2026-01-01","expiration_date":"2026-12-31","status":"active"}'
```

Required fields are `policy_number`, `holder_name`, `plan_type`,
`effective_date`, and `expiration_date`. Status defaults to `active`; allowed
statuses are `active`, `inactive`, and `expired`. Optional `coverages` accepts
up to 50 rows with `coverage_type`, `covered_services`, `exclusions`,
`deductible`, `copay`, `coinsurance_percent`, `out_of_pocket_max`, and
`annual_limit`. Cost amounts are nonnegative and coinsurance ranges from 0–100.
Reversed policy dates return 422; duplicate policy numbers return 409.

The response contains the policy UUID and public metadata. List responses use
`items`, `total`, `limit`, and `offset`. `indexing_status` is `not_indexed`
until a successful ingestion is persisted; `indexed` represents that recorded
success, not an independent live Qdrant health check. Filesystem paths and full
parsed documents are omitted from list responses.

```bash
curl -X POST http://localhost:8000/api/v1/policies/<policy_id>/upload \
  -F 'file=@./policy.pdf'
```

PDF uploads use `MAX_UPLOAD_SIZE_MB` (25 MB by default) and Docling's configured
page limit (500 by default). Empty or invalid PDF headers return 400; oversized
files return 413; incomplete parsing returns 422; indexing/service failures
return 503. Unknown policy IDs return 404. Saved PDFs use generated filenames
under the shared upload directory. Inputs are retained after indexing failures
to avoid deleting a document whose database commit outcome is uncertain.

Ingestion completes within the request using the existing Phase 2 service.
The frontend shows progress while awaiting the result, allows up to 30 minutes,
and then refreshes the policy list. A successful response contains `policy_id`,
`indexing_status`, `page_count`, `chunk_count`, and `message`. Refresh the
repository after an uncertain connection failure before uploading again.
Replacing a PDF uses the same policy-scoped indexing and revision publication
rules documented in [the RAG guide](rag.md). Directory ingestion remains a CLI
operation; no endpoint accepts arbitrary server directory paths.

## Analytics definitions

Summary metrics are calculated from PostgreSQL records. `by_status` includes
every claim status, including zero counts. `auto_approved` counts approved
claims with an automatic final decision record. `fraud_flagged` counts
assessments at or above the current configured screening threshold, without
asserting fraud. `human_decisions` counts accepted reviews, including those
still awaiting application. `override_rate` is overrides divided by accepted
reviews and is null when there are none.

`average_completion_seconds` measures submission to the `claim_decided` event,
including human review wait. It is null until a recorded final decision exists.
Policy counts reflect metadata and recorded ingestion success. `recent_claims`
contains five public claim records; `recent_events` contains eight event
headers with claim links and timestamps, without full event payloads.

Trends return `days`, `timezone` (`UTC`), and `points`. Every day in the period
is included, with zero counts where appropriate. Each point contains `date`,
`submitted`, `decided`, `human_decisions`, `overrides`, and
`average_completion_seconds`. Submissions use submission date; decisions use
decision date; accepted reviews and overrides use acceptance date.

The examples above document API usage and have not been executed. The Phase 5
frontend production build and static source checks passed; no tests were run.
