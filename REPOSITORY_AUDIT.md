# CartPilot repository audit

Audit date: 23 October 2026. Baseline: `7d19283d3fe8ef76f3f05e0f4f4a90ec3c466a26`.
Scope: the existing application, not a replacement. This release audits and plans;
it does not implement forecasting, reservations or other proposed platform features.

## Method and evidence

All 384 tracked files were read for a reproducible inventory: 360 text files and
24 binary assets/deliverables. Python syntax/symbols, routes, models, migrations,
test definitions, frontend modules, configuration, documentation and phase records
were inventoried. Manual review traced the security, commerce, recommendation,
specialist, orchestration and deployment paths identified below. This is a repository
engineering audit, not a claim of exhaustive line-by-line vulnerability discovery,
penetration testing or manual revalidation of binary academic reports.

The [file inventory](docs/audits/2026-10-23-repository-inventory.json) records baseline
hashes and scope. Ignored `.env` files, installed dependencies, local databases and
generated builds are excluded. Documentation and old JSON reports are historical
evidence, not proof that a feature currently works. There is no root `tests/`
directory; tests live in `backend/tests/` and `frontend/tests/`.

Fresh checks on Apple Silicon arm64, Python 3.12.7, Node 26.10.0/npm 11.19.1:

| Check | Actual result |
| --- | --- |
| Backend `venv/bin/python -m pytest -q` | 738 passed, 5 opt-in PostgreSQL tests skipped, 39.78 seconds |
| Frontend `npm run test:run` | 174 passed in 21 files |
| Frontend `npm run build` | TypeScript and Vite pass; main JS 286.95 kB / 85.04 kB gzip |
| Python `pip check` | No broken requirements; this is dependency consistency, not a security scan |
| npm full dependency audit | 13 affected package entries: 2 critical, 6 high, 5 moderate; exits 1 |
| npm production-only audit | 0 findings; does not clear build/test tooling risks |
| Pinned Python `pip-audit` | 2 advisories in 2 packages; exits 1 |
| PostgreSQL concurrency | Five targeted tests passed on disposable PostgreSQL 17.11; startup initially used the wrong port, then corrected to 55439 |

CI uses Python 3.12, Node 24 and PostgreSQL 17. Fresh remote results for this publication
must be checked independently. No fresh browser UAT, live provider calls, load benchmark,
backup restore or production database mutation was performed for this audit. Existing
Phase 18 browser and migration reports remain explicitly dated prior evidence.

## What exists and what does not

| Area | Code-backed finding | Main evidence |
| --- | --- | --- |
| Identity and store isolation | Scrypt passwords; hashed, revocable eight-hour sessions; production account gate and merchant comparisons; one account per merchant | `api/v1/accounts.py`, `models/account.py`, `test_accounts_management.py`, `test_auth_limits.py` |
| Catalog and sales | Scoped local CRUD/archive, atomic CSV sales/catalog imports, read-only Shopify cache integration; no stock decrement on sales import | `api/v1/management.py`, `commerce/ingestion.py`, `integrations/shopify/`, management/Shopify tests |
| Shopping persistence | SQL carts, snapshots, audit events, chat and recovery records exist; browser tab capability lasts one hour, quote 15 minutes | `models/commerce*.py`, `commerce/carts.py`, `services/commerce.ts`, workflow/session tests |
| Inventory reservations | Existing inventory has source reserved/unavailable counters; checkout only reads availability; no cart-linked reservation lifecycle | `models/inventory.py`, `commerce/carts.py`, `api/v1/commerce.py` |
| Payments | Simulation/test Razorpay links; signed bound webhooks, pending claims, manual reconciliation, refunds/cancellation/return review | `commerce/payments.py`, `commerce/resolution.py`, commerce tests and five PostgreSQL checks |
| Orders | Sales/import/cache records have statuses; no checkout-to-order relation, fulfillment transitions, allocation/expiry/returns accounting | `models/order.py`, `models/order_item.py`, `api/v1/management.py`, Shopify sync |
| Merchant specialists | Deterministic pricing/restock/promotion/listing algorithms, typed inputs, current-state policy validation, conflict rules | `agents/`, `services/{pricing,restock,promotion,listing,policies,orchestration}/`, specialist/action tests |
| Orchestration | Synchronous request plan and saved summary; guarded Action/Approval/AuditLog workflow; no resumable node execution | `agents/orchestrator.py`, `orchestration/history.py`, `actions/workflow.py` |
| Discovery | Lexical/category/co-purchase/compatibility/business ranking; optional Gemini/OpenAI structured intent; optional semantic index | `commerce/catalog.py`, `learning.py`, `providers.py`, `api/v1/commerce.py` |
| Learning | Explicit experimental 64D Item2Vec, 30-order minimum; JSON vectors and catalog fingerprints | `commerce/learning.py`, `test_commerce_learning.py` |
| Forecasting/MLOps | No LightGBM/XGBoost forecasting pipeline, time-split evaluation, uncertainty calibration, MLflow registry or model promotion gates | Dependency manifests, services/models and complete test index |
| Personalization/LTR | Basket-anchor association exists; persistent consenting buyer profiles, impression labels, exposure-aware LTR and evaluated personalized ranking do not | Shopper model, ranking inputs and event schema |
| Multimodal | Text embeddings only; no validated image ingestion, image vectors, image/text retrieval or image evaluation set | Product model, search schemas and provider/index code |
| Merchant experience | Live React workspace, approval/audit pages, saved activity, buyer chat and Commerce Studio; no forecast/model-health dashboard | `frontend/src/pages/`, components, typed clients and frontend tests |
| Operations | Alembic, Docker/Compose, Vercel API proxy, GitHub tests/build/PG job, liveness/detailed health; optional workers are code, not hosted durable infrastructure | `.github/workflows/ci.yml`, host/container configs, health/worker tests |

Paths in the table are relative to `backend/app/`, `backend/tests/` or `frontend/src/`
as applicable. Existing stock, price, scope, audit and test-payment guardrails are
valuable foundations and must remain in place throughout the upgrade.

## Findings and release risks

Severity describes potential consequences when expanding deployment, not proof of
an exploited live vulnerability. Confirmed means directly observed in source or tools;
unverified means further testing is required. Priority is implementation order.

| ID | Priority / evidence | Finding and required response |
| --- | --- | --- |
| A01 | P0 / confirmed absence | Stock checks do not allocate inventory. Independent carts can both pass against the same stock. Add atomic cart-linked expiring leases and concurrent last-unit tests before treating checkout as fulfillment-capable. |
| A02 | P0 / confirmed absence | Test settlement never creates an order. Add a separately classified test-order lifecycle, unique checkout/order binding, accounting and explicit transitions without contaminating imported real sales. |
| A03 | P0 / confirmed advisories | Full npm audit finds vulnerable Vite/Vitest/Tailwind transitive tooling, including critical Vitest/tinypool entries. `vite.config.ts` uses `host: true`, increasing local exposure. Remediate with tested compatible upgrades; bind dev tools to loopback. Do not run `npm audit fix --force` blindly. Static production assets are not a running Vitest server. |
| A04 | P0 / confirmed advisories | Python constraints pin certifi 2026.7.22 (PYSEC-2026-4320; scanner recommends >=2026.10.19) and opentelemetry-api 1.45.0 (CVE-2026-114603; >=1.45.1). Certifi affects trust for external HTTP. OpenTelemetry exploit reachability is not established: application instrumentation is absent. Update/re-audit in a tested dependency change; no claim of active exploitation. |
| A05 | P0 / source-backed gap | Payment claims survive provider calls, but no durable webhook inbox, outbox/retry queue or scheduled reconciliation exists. A webhook before the link ID is saved returns a rejection; provider listing/refund scans are bounded to 100. Build replayable event ingestion, explicit unknown/dead-letter states and crash-window tests. |
| A06 | P0 / source-backed gap | Several cart paths read/reconcile state then commit across a provider call. A prior row lock ends at that commit. Add post-call compare-and-set/lock revalidation and race tests against webhook/cancel/refund/recovery; current five concurrency tests do not establish all interleavings. |
| A07 | P1 / confirmed design | Sessions are bearer capabilities in sessionStorage, readable by same-origin JavaScript; no MFA, verified email, password-reset delivery or staff roles. Retain scope checks; threat-model XSS/token theft, session revocation and privileged reauthentication. Cookie migration would require CSRF design and MCP compatibility, not a mechanical swap. |
| A08 | P0 / deployment gap | Application limits use ASGI peer identity, with provider trust configuration external. Some original cart GET/approve/checkout/audit routes lack `public_limit`; webhook limits differ. Validate proxy identity, body/header size and cost budgets for every public/expensive route. Auth limiting parses JSON before schema validation; no universal streamed body cap exists. |
| A09 | P1 / confirmed design | Supplier URL checks reject literal private addresses but do not resolve/pin DNS addresses. Owner-only configured endpoints reduce exposure but do not provide a DNS-rebinding egress boundary. Add outbound allowlisting/validated resolution and network controls before broader supplier configuration. |
| A10 | P0 for ML / confirmed absence | Sales may be seeded, manually imported or Shopify-cached; checkout tests are separate today, but orders lack an explicit provenance/training-eligibility field. No historical stock-availability or price-at-observation feature store exists. Establish provenance, as-of snapshots and stockout censoring before training. |
| A11 | P1 / confirmed absence | Item2Vec saves over `(merchant_id, kind)` without retained dataset hash, immutable versions, holdout metrics or rollback registry. Semantic vectors are fingerprinted but JSON scans and request-time calls remain bounded prototypes. Preserve baseline while adding versioned evaluation and serving contracts. |
| A12 | P1 / confirmed defect in parity | Merchant `merchandising.preview()` omits saved category-compatibility scores used by shopper `commerce.search()`. Therefore the preview is not an exact preview of the shopper ranking pipeline. Consolidate the ranking service and add contract parity tests. |
| A13 | P1 / confirmed scale defect | Commerce worker selects the first 100 enabled merchant IDs, not the next due work across all merchants. Stores beyond that bound can starve. Add due ordering, pagination/leases, restart and multiworker tests. Expiry/retention cleanup is also not a hosted service. |
| A14 | P1 / confirmed performance concern | Audit dashboard performs event/operation reads per cart; hash append loads full history. Both are bounded or per-cart today, but query/latency growth is not benchmarked. Batch ledger reads, paginate and profile before adding dashboard traffic. |
| A15 | P1 / confirmed operational gap | Safe exception-class logs and health exist, but request correlation, service metrics/traces, alerting, worker heartbeat, model drift/quality and incident/backup drills do not. Detailed readiness returns HTTP 200 even when degraded. Monitor its payload until a separate readiness contract is introduced. |
| A16 | P1 / confirmed test gap | CI tests happy/failure/boundary paths and five PG scenarios, but no coverage threshold, static lint/type gate for Python, SCA job, automated browser CI, migration drift check, load/chaos test or ML evaluation suite. Test counts are not coverage percentages. |
| A17 | P1 / confirmed deployment gap | Vercel 60-second handlers cannot host permanent training/checkpoint workers; Docker Compose does not wire the new commerce provider settings or commerce worker. Model weights/downloads/native ML runtime are unverified. Keep training offline and provision durable worker capacity only when needed. |
| A18 | P1 / confirmed consistency gap | Currency is INR in buyer commerce; supplier numeric prices are interpreted as INR with a warning; merchant formatting can use another build currency. Add a server currency contract and block incompatible publication/import; no silent FX conversion. |
| A19 | P2 / confirmed maintainability | Commerce services import route functions (`conversation.respond`, merchant recovery handoff), mixing HTTP and domain layers. Several TSX components have compressed single-line JSX and broad string statuses. Extract typed domain services and readable components incrementally with characterization tests. |
| A20 | P1 / confirmed DB gap | Commerce status/money/quantity invariants mostly live in schemas; commerce tables lack matching status/check constraints and cart item normalization. Existing inventory checks do not constrain reserved+unavailable <= physical. Add compatible constraints after legacy-data preflight; preserve source reservation semantics. |
| A21 | P1 / confirmed retention gap | Expired shopper tokens stop authorizing, but chat/carts/operations/handoffs persist without a documented retention/deletion job. One-hour capability expiry also prevents permanent buyer access. Design identity/consent and financial-audit retention separately; do not cascade-delete financial history during cleanup. |

Dependency evidence: [npm](docs/audits/2026-10-23-npm-audit.json),
[production-only npm](docs/audits/2026-10-23-npm-production-audit.json),
[Python](docs/audits/2026-10-23-python-audit.json). Package entries are not independent
exploits; severity comes from advisory databases. Optional ML dependencies were not
installed or transitively audited. Source/lock secret scanning is limited to configured
values and obvious patterns, not a forensic scan of all Git history or host secrets.

## Documentation corrections

Phase 18 is already implemented; the new initiative begins with audit/planning and
proposes phases 19–27. Do not overwrite the existing Phase 18 migration or history.
`ARCHITECTURE.md`'s Phase 17 MCP paragraph and README's foundation bullet were stale:
current MCP contains owner growth tools and browser financial handoff. It cannot
authorize a payment. Current sections now identify that distinction.

Older phases, final academic deliverables and deployment handoff files describe their
own dates. They must not override current code or the upgrade progress ledger. Existing
"verified" algorithm formulas are deterministic business rules, not forecast accuracy.
Optional OpenAI/Gemini/MiniLM paths are implemented with mocked tests, not verified live
model quality. Prior deployment success does not clear the advisories found today.

## Recommended sequence

First address dependency/public-surface risks and reservation correctness; then order
state/idempotent payment processing and trustworthy event lineage. Train/evaluate demand
baselines and a gradient-boosted candidate offline before adding model serving. Instrument
recommendation exposure before LTR; introduce durable orchestration without bypassing
Action/Approval; then image retrieval, bounded optimization and merchant explanation
views. Operational instrumentation starts in phase 19 and is completed with monitoring,
restore/load drills and promotion gates in phase 27. See the five UPGRADE documents.
