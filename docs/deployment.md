# LiteLLM with any OpenAI-compatible API

## Phase 5 backend, worker, and frontend

The backend Dockerfile now installs the application dependencies and a CPU
PyTorch build. The Compose worker uses `app.celery_app:celery_app`, and the
backend and worker share the `claim_uploads` volume at `/app/uploads` and the
Hugging Face model cache. Keep `UPLOAD_DIR=/app/uploads` inside these containers.

Run the implemented workspace services:

```bash
docker compose up --build -d postgres qdrant redis litellm backend celery-worker frontend
docker compose exec backend alembic upgrade head
```

Apply application migrations before submitting claims. LangGraph checkpoint
tables and the claim vector collection initialize when the worker first needs
them. These startup commands have not been executed during implementation.
For host execution, agent configuration, and checkpoint setup commands, see
[the agent guide](agents.md). FNOL and review routes are documented in [the API guide](api.md).

Phase 4 uses the existing application tables, so it adds no Alembic migration.
Phase 5 also reuses the existing tables for policies and analytics.
Restart backend and worker after updating the code. Previously `triaged` claims
can be queued for specialized assessment using their claim retry endpoint.

For medical reference matching, mount an organization-maintained catalog in the
worker and set `MEDICAL_CODE_REFERENCE_PATH` to its container path. The required
JSON format is in [the agent guide](agents.md). For example, a local Compose
override can add `./references:/app/references:ro` to `celery-worker.volumes` and
use `/app/references/medical_codes.json`. Without an applicable reference file,
medical claims pause for human coding review. Set `FRAUD_HISTORY_DAYS` and
`FRAUD_HISTORY_LIMIT` to configure the database screening window.

The development frontend runs Vite at `http://localhost:3000` and proxies API
requests to the backend service. The production Compose file selects the Nginx
Docker target, which serves built assets and supports direct claim-detail URLs:

```bash
docker compose -f docker-compose.prod.yml up --build -d
```

For local frontend settings, request limits, and workflow behavior, see
[the frontend guide](frontend.md). The frontend was compiled during Phase 5;
containers, live services, and tests were not run.

The intake model must accept image data URLs. Configure `INTAKE_MODEL` and
`TRIAGE_MODEL` with LiteLLM model aliases. `LLM_JSON_MODE=prompt` disables the
JSON response-format request for providers that do not support it, while
retaining Pydantic output validation.

The proxy exposes a stable `claims-model` alias for all agents. Its upstream
API base URL, model ID, and API key are configurable through `.env`, so changing
the upstream does not require application code changes.

Compose adds the `openai/` prefix to the model ID, following the
[LiteLLM OpenAI-compatible endpoint documentation](https://docs.litellm.ai/docs/providers/openai_compatible).
This prefix selects the API protocol; the upstream can be local, hosted, or
an in-house router.

## Configure the upstream

If a local `.env` does not exist, copy `.env.example` to `.env`. Configure:

```dotenv
LLM_API_BASE=https://your-provider.example/v1
LLM_MODEL=your-provider-model-id
LLM_API_KEY=your-provider-api-key

LITELLM_BASE_URL=http://litellm:4000/v1
LITELLM_API_KEY=sk-local-dev-key
```

| Variable | Purpose |
| --- | --- |
| `LLM_API_BASE` | Upstream API base URL as reached from the LiteLLM container |
| `LLM_MODEL` | Exact upstream model ID, without LiteLLM's `openai/` prefix |
| `LLM_API_KEY` | Upstream credential; use `not-needed` for an unauthenticated local server |
| `LITELLM_BASE_URL` | Proxy API base URL used by the backend |
| `LITELLM_API_KEY` | Client credential for the proxy, also supplied as its master key |

Use the provider's base URL, typically ending in `/v1`. Do not append
`/chat/completions`; the OpenAI client adds that endpoint. Preserve model IDs
containing slashes: `LLM_MODEL=organization/model-name` is forwarded with that
ID after LiteLLM removes its provider prefix.

Replace example endpoint and model values before use. The upstream and proxy
credentials are separate: `LLM_API_KEY` authenticates with your provider, and
`LITELLM_API_KEY` authenticates with LiteLLM.

## Local servers

For a local OpenAI-compatible server listening on host port 8001, use:

```dotenv
LLM_API_BASE=http://host.docker.internal:8001/v1
LLM_MODEL=your-served-model-id
LLM_API_KEY=not-needed
```

Both Compose files map `host.docker.internal` to Docker's host gateway.
The local server must listen on an interface reachable from Docker.
For a server in the same Compose network, use its service hostname and
container port instead.

## Start or reconfigure the proxy

From the repository root:

```bash
docker compose up -d litellm
```

After changing upstream settings in `.env`, recreate the proxy:

```bash
docker compose up -d --force-recreate litellm
```

Both Compose files mount `litellm/config.yaml` read-only and pass all upstream
settings to LiteLLM. The YAML uses LiteLLM's
[environment variable configuration](https://docs.litellm.ai/docs/proxy/configs).
Streaming is selected by each request.

## Backend settings

| Backend location | `LITELLM_BASE_URL` |
| --- | --- |
| Compose backend or worker | `http://litellm:4000/v1` |
| Python on the host | `http://localhost:4000/v1` |

For host development:

```bash
source ~/anaconda3/bin/activate
conda activate llmDev
export LITELLM_BASE_URL=http://localhost:4000/v1
```

All eight agent model settings default to `claims-model`. These settings refer
to proxy aliases; add additional entries in `litellm/config.yaml` before
assigning an agent to another alias. Changing `LLM_MODEL` switches the shared
upstream model for every agent using `claims-model`.

The upstream must support the features used by a request. Image intake
requires a vision-capable model accepting chat `image_url` content parts;
structured extraction requires compatible JSON or schema output support.
API compatibility alone does not add these capabilities to a model.
