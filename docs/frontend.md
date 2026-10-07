# Phase 5: Claims workspace

The frontend is a Vue 3 application with Vite, Vue Router, and Pinia. All
dashboard figures and claim data come from the backend; no demo records are
inserted. The interface includes desktop navigation, a mobile drawer, keyboard
focus indicators, error and empty states, and accessible chart data tables.

## Run locally

Use Node.js 22.12 or newer. From the repository root:

```bash
cd frontend
npm ci
npm run dev
```

Open `http://localhost:3000`. By default, Vite forwards `/api` to
`http://localhost:8000`. Start the backend, worker, and backing services with
the same application settings, and apply the existing database migrations.
See [deployment](deployment.md) and [agent operation](agents.md).

Optional frontend settings are in `frontend/.env.example`. Copy these to
`frontend/.env.local` when needed. `API_PROXY_TARGET` controls the Vite server's
backend destination. `VITE_API_BASE_URL` controls the browser API base, defaulting
to `/api/v1`; browser variables must not contain secrets. Use an absolute API
base only when deliberately accessing a separate origin. Evidence URLs use
the same configured API base.

```bash
npm run build
npm run preview
```

Build output is in `frontend/dist`. Vite preview serves compiled assets only;
it does not proxy the API. Use the production Nginx container for a complete
same-origin deployment, or configure an absolute API base before building.
`npm run format` formats frontend source with Prettier.

## Workspace routes

| Route | Features |
| --- | --- |
| `/` | Claim metrics, status distribution, 30-day activity, recent claims and events |
| `/claims` | Server search, status/date filters, pagination, claim links |
| `/claims/new` | Narrative entry, drag-and-drop images, attachment previews, configured limits |
| `/claims/{id}` | Extracted fields, original images, agent assessments, report, timeline, review history |
| `/reviews` | Paused claims, review reasons, links to decision controls |
| `/policies` | Metadata creation, search, PDF upload/replacement, recorded ingestion status |
| `/analytics` | 7/30/90-day activity, all-time metrics, daily performance table |

Narrative and image limits are loaded from `/claims/intake-settings`. The UI
checks image types, counts, and combined size; the backend additionally checks
actual image contents and pixels. A submission is disabled while intake runs.
If dispatch fails after saving the claim, the interface links to that existing
claim so the user can resume processing instead of creating a duplicate.

Claim detail refreshes while processing or awaiting review. Completed claims
remain available for manual refresh. Assessments distinguish missing fields,
uncertain coverage, potential duplicates, reference matching, and screening
scores. The report renders Markdown through a restricted DOMPurify sanitizer;
it can also be downloaded as the original Markdown. Raw submissions and
structured assessment output render as text. Amounts have no invented currency
label because the current backend schema does not identify a currency.

Human review displays original evidence and the assessment alongside decision
controls. A reviewer enters an identifier and selects approve, reject, or an
override target. Rejections and overrides require notes. A second confirmation
records the decision, then the UI follows its application and retained history.
The identifier is caller-supplied under the existing authentication scope.

Policy uploads first require a metadata record. A PDF is parsed and indexed
within the upload request, with a progress indicator and a 30-minute client
timeout. Navigation within the app is paused while submission or ingestion is
pending. A document's repository flag represents its last recorded successful
ingestion. Large PDF conversion uses the backend's CPU Docling and embedding
services. Policy cost-sharing rows can be supplied through the metadata API;
the frontend form covers identity, plan, status, and term dates.

## Refresh and deployment behavior

The dashboard refreshes every 20 seconds, the register and review queue every
15 seconds, active claim detail every 5 seconds, policy metadata every 20
seconds, and analytics every 30 seconds. Reads pause when the page is hidden.
Polling schedules from request completion, queues manual refreshes, and aborts
reads on unmount. Request serials prevent older responses from replacing newer
filters or claim details. No WebSocket service is required.

Compose development selects the frontend `development` Docker target, runs
Vite, and sets `API_PROXY_TARGET=http://backend:8000`. Production selects
`production`, serves the compiled application with Nginx on port 3000, proxies
`/api` to the backend, and falls back to `index.html` for deep links. Hashed
assets are cached; the application shell is not. Nginx allows 100 MB request
bodies; adjust `client_max_body_size` when using larger backend upload limits.

The production build and backend static syntax checks passed during Phase 5.
Tests, service startup, browser interaction, and end-to-end verification were
not run, following the instruction to avoid tests.

## References

- [Vite development and production builds](https://vite.dev/guide/)
- [Pinia store definitions](https://pinia.vuejs.org/core-concepts/)
- [Lucide Vue components](https://lucide.dev/guide/vue/getting-started)
