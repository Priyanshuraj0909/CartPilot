# CartPilot upgrade roadmap

All phases below are **planned, not implemented**. The completed planning milestone
is recorded in [progress](UPGRADE_PROGRESS.md). Phase 18 remains historical commerce
parity; no renumbering of its migration or replacement of working features.
Each phase uses the delivery protocol in [master plan](UPGRADE_MASTER_PLAN.md).

## Phase 19 — Cart integrity, reservations and initial hardening

Problem: carts persist but independent checkout requests only check stock; there is no
owned allocation to expire, consume or release. Current dependency advisories and
public request-budget gaps also block a production-readiness claim (A01, A03–A04, A08).

Affected existing paths: `backend/app/models/{inventory,commerce}.py`,
`services/commerce/{carts,catalog}.py`, `api/v1/{commerce,management}.py`,
`schemas/commerce.py`, new Alembic revision, commerce/PG/migration tests,
`frontend/src/pages/Buyer.tsx`, `components/CartResolution.tsx`,
`services/commerce.ts`,
dependency constraints, `frontend/package*.json`, `vite.config.ts` and CI as required.

Smallest solution: characterize legacy routes, introduce opt-in sandbox allocations
and central availability service with atomic pool-row locking, version-bound approval,
lease expiry/release worker and idempotent transitions. Preserve source inventory counters
and default simulation. Preflight invalid inventory before constraints. Fix dependency
advisories with bounded tested upgrades; loopback dev serving, streamed size limits and
consistent public/cost budgets. Add request correlation and worker heartbeat foundations.

UI: show reservation expiry, refresh/review after changed quote, sold-out conflicts and
explicit simulation labels; no implied stock guarantee for legacy carts.
Tests: concurrent last unit/multi-product lock ordering, edit invalidation, expiry at the
boundary, repeated release, process crash, tenant mismatch, source reserved stock, disabled
flag compatibility, limits/provider failures and dependency/build regressions.
Exit: no negative/duplicate allocations in PG; legacy flows retained; docs and release checks pass.
Suggested commits: `fix: remediate audited dependency and public-surface risks`,
`feat: add scoped expiring sandbox inventory allocations`.

## Phase 20 — Test orders and replayable payment processing

Problem: settlement has no fulfillment order and no inbox/outbox; partial failures and
the provider-call/DB-commit window require recovery (A02, A05–A06, A10, A20–A21).
Affected: `models/order*.py`, proposed commerce order/payment/event/job models,
`commerce/{payments,resolution,ledger}.py`, webhook/merchant APIs, migrations,
`CartResolution.tsx`, proposed OrderHistory/OrderDetail components and typed clients.

Smallest solution: separate test-order state from historical sales, one immutable order
per cart/payment, durable normalized webhook inbox and SQL outbox/job leases; reconciliation
reads authoritative state with bounded retries and explicit unknown/manual-review results.
Capture source/environment/currency/event lineage now for downstream data quality.
Keep test stock movements isolated; returns, refunds and receipt remain separate decisions.

UI: test order timeline, payment/fulfillment status shown separately, reconciliation
progress/unknown state and return review. Approval and checkout confirmation remain distinct.
Tests: duplicate/out-of-order webhook, webhook-before-link-save, provider success/DB failure,
worker death/reclaim, amount/currency mismatch, cancel-versus-paid/refund races, repeated
fulfillment/release, cross-tenant ID/key and partially returned/refunded totals.
Exit: transactional effect deduplication demonstrated, imported sales unaffected, live mode impossible.
Suggested commit: `feat: add idempotent test orders and replayable payment events`.

## Phase 21 — Reproducible demand forecasting

Problem: velocity heuristics and experimental Item2Vec are not demand forecasts; eligible
historical data and time-aware evaluation are missing (A10–A11).
Affected: new `backend/ml/` offline package/optional pinned requirements, dataset/model
metadata migrations, forecast read service/API, existing pricing/restock signal adapters,
new evaluation tests/fixtures and forecast UI section when a valid read API exists.

Smallest solution: versioned daily as-of dataset and seasonal/intermittent baselines;
offline CPU LightGBM challenger, XGBoost comparison only if useful. Track manifests,
parameters/metrics/artifacts with local MLflow; serve stored forecast results with baseline
fallback. Keep native training libraries outside hosted API. Do not train on demo outcomes
and present them as merchant performance. Minimum history/cohort criteria must be set
from observed data and documented before a training run, not guessed as an accuracy claim.

Tests: lag/rolling leakage, overlapping horizon purge, late-arriving data, missing days,
stockouts, zero demand, new SKU, insufficient history, model/artifact/schema mismatch,
repeatable run, failed load and latency/memory. Record MAE/WAPE/MASE/pinball/coverage by
horizon/cohort where denominators are valid; never replace baseline on test-set tuning.
Exit: reproducible untouched holdout report, cold-start/uncertainty/latency limits and rollback.
Suggested commit: `feat: add time-aware demand baselines and tracked forecast experiments`.

## Phase 22 — Unified retrieval, session personalization and LTR

Problem: ranking is heuristic, preview differs from shopper search, and there are no
exposure/label contracts or durable consenting buyer profiles (A11–A12, A21).
Affected: `commerce/{catalog,learning,merchandising,conversation}.py`, search APIs/schemas,
CommerceModel/event metadata, search/preview clients and tests; optional vector migration.

Smallest solution: shared eligibility/ranking domain service; merchant-scoped impressions,
consented session interactions, model/version explanations and deterministic fallback.
Benchmark current hybrid and exact vector retrieval; introduce pgvector only if needed.
Collect mature labels before training an XGBoost/LightGBM ranker; evaluate query groups
with temporal splits and exposure caveats. No fabricated click negatives from unseen products.

UI: readable ranking reasons, session-personalization preference, merchant preview parity
and sample-size/freshness labels. Tests: shared pipeline parity, privacy/tenant isolation,
new user/product, deleted consent/history, stale vectors, missing candidate, delayed label,
provider outage, candidate Recall@K and NDCG@K/MRR by held-out group plus latency.
Exit: reproducible baseline comparison and safe fallback; otherwise keep experimental mode.
Suggested commit: `feat: unify explainable retrieval and instrument recommendation evaluation`.

## Phase 23 — Durable specialist orchestration

Problem: saved summaries cannot resume interrupted specialist nodes, approvals or retries
(A15, A17, A19). Existing guarded Action/Approval is retained.
Affected: `agents/orchestrator.py`, orchestration services, `models/agent_run.py`,
action adapters, run/job/checkpoint migrations, AIManager/AgentActivity/Approvals UI.

Smallest solution: typed persisted run/node state, deterministic input snapshot and
leased SQL jobs; prototype one pause/review/restart path. Compare small SQL state machine
with optional LangGraph Postgres checkpoints and adopt only with documented benefit.
LLM nodes generate proposals; validation/review/execution stays in application tools.

UI: step timeline, waiting-for-review, retry/partial-result/restart visibility, stale
approval prompts and scoped trace. Tests: kill/restart every side-effect boundary,
replay, expired worker lease, duplicate review, changed product/policy, partial specialist
failure, malformed model output and attempted model authorization.
Exit: resumed execution cannot bypass current policy or human confirmation.
Suggested commit: `feat: persist resumable specialist workflows with guarded review`.

## Phase 24 — Multimodal product discovery

Problem: current product/search contracts contain no image asset or embedding pipeline.
Affected: product asset/embedding models and migrations, new scoped media validation/
index/search services, optional offline encoder requirements, Buyer image search UI/tests.

Smallest solution: controlled bounded image upload/storage and content hashes; locally
evaluate a licensed image/text encoder, exact search first, reuse phase 22 eligibility and
model-version contracts. Keep binary decoding/indexing out of long serverless requests.
UI: accessible upload/preview, text alternative, delete control and honest similarity reasons.
Tests: false MIME, malformed/decompression-bomb/oversized image, tenant ID, stale asset,
deleted image, model mismatch, image/text retrieval relevance, cold catalog and latency.
Exit: safe bounded media handling and measured retrieval report, text fallback available.
Suggested commit: `feat: add validated tenant-scoped image retrieval`.

## Phase 25 — Forecast-informed inventory and pricing scenarios

Problem: current rules use fixed lead/safety assumptions and no uncertainty-aware shared
budget scenarios; forecasts alone cannot estimate causal price elasticity.
Affected: restock/pricing signal and rule adapters, policy validator, proposed scenario
service/schemas/results, approval cards and scenario UI; optional optimization requirement.

Smallest solution: read-only scenario comparisons using approved forecasts/quantiles,
merchant-specified costs/lead time/capacity and bounded prices/quantities. Baseline heuristic
first; evaluate OR-Tools only for coupled budget/MOQ/capacity constraints. Preserve hard
inventory overrides, known-cost floor, risk caps, explicit review and fresh confirmation.
Tests: unknown cost/elasticity, infeasible MOQ/budget, integer/cent rounding, solver timeout,
stale forecasts, new SKU, source data changes, boundary caps and approved payload tampering.
Exit: feasibility and sensitivity explained; no autonomous price/promotion/purchase-order writes.
Suggested commit: `feat: add guarded forecast-informed planning scenarios`.

## Phase 26 — Merchant intelligence product experience

Problem: merchant views show descriptive sales and rules but lack forecast/model evidence.
Affected: existing Dashboard, Inventory, AIManager, GrowthConsole/CommerceStudio,
typed read APIs/clients and reusable explanation/chart/timeline components.

Smallest solution: extend navigation with observed/forecast distinctions, inventory risk,
model version/freshness, uncertainty, source/sample-size and reason components; batch and
paginate analytics/ledger reads. Keep historical views and all existing commerce controls.
Select chart dependency only after checking whether current SVG/CSS satisfies the need.
Tests: empty/partial/error/stale data, keyboard/focus and labels, 390/768/1440 layouts,
merchant switch, loading cancellation, confirmation separation and real-browser workflows.
Exit: no false causal-revenue/accuracy labels or hidden sensitive actions.
Suggested commit: `feat: explain forecasts and commerce decisions in merchant analytics`.

## Phase 27 — Operational and model-monitoring qualification

Problem: current CI/deployments do not prove public production reliability (A07–A09,
A13–A18, A21); monitoring/security work from preceding phases needs a release exercise.
Affected: main middleware, health/auth/egress/worker modules, host/container configs,
CI/security/dependency automation, ML monitor jobs, deployment/backup/incident runbooks.

Smallest solution: complete scoped redacted telemetry and alerts, data/model freshness
and delayed-label performance checks, durable worker hosting/leases, dependency review,
retention controls and backups/restore. Add browser/PG/migration/ML gates proportionate
to changed components; define ownership and SLOs before claiming readiness.
Tests: target load, DB/provider outage, retry storm, worker loss, model drift/staleness,
backup restoration, deploy/rollback, oversize/tenant/identity/egress security cases and
authenticated hosted UAT with owner-approved test data. No live charges.
Exit: published evidence for measured capacity/latency, response procedures and rollback;
remaining risks explicitly accepted or readiness remains incomplete.
Suggested commit: `chore: qualify monitored deployment and model rollback procedures`.

## Apple Silicon development commands

Current verified machine: arm64, Python 3.12.7, Node 26.10.0. CI uses Node 24; prefer
Node 24 for reproducibility. These are exact local-development commands, not proof
that a fresh machine/container was tested. Never reuse a hosted DATABASE_URL for local
migration/seed/integration tests. Preserve any existing `.env` file.

```bash
cd /Users/priyanshuraj/Projects/cartpilot
brew install python@3.12 node@24 postgresql@17
export PATH="/opt/homebrew/opt/python@3.12/bin:/opt/homebrew/opt/node@24/bin:/opt/homebrew/opt/postgresql@17/bin:$PATH"
test -f .env || cp .env.example .env
```

Use the existing Docker Compose PostgreSQL service with Docker Desktop running.
The alternate port avoids the machine's existing PostgreSQL on 5432:

```bash
POSTGRES_PORT=55432 docker compose up -d postgres
export ENVIRONMENT=development
export DATABASE_URL='postgresql+asyncpg://cartpilot:cartpilot@127.0.0.1:55432/cartpilot'
export REDIS_URL=''
cd backend
python3.12 -m venv venv
venv/bin/python -m pip install -r requirements.txt -c requirements.lock.txt
venv/bin/python -m alembic upgrade head
# Only on the new disposable local database; skip seed for an existing valued store.
venv/bin/python -m app.core.seed
venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Compose can read customized POSTGRES_* from an existing `.env`; if those differ, use
that service's local credentials in the export above. Do not copy hosted credentials.
In a separate terminal:

```bash
cd /Users/priyanshuraj/Projects/cartpilot/frontend
export PATH="/opt/homebrew/opt/node@24/bin:$PATH"
npm ci
npm run dev -- --host 127.0.0.1
```

Current regression commands and a native Homebrew PostgreSQL isolation recipe are in
[test strategy](UPGRADE_TEST_STRATEGY.md). Docker runtime was not revalidated in this
audit; native PostgreSQL concurrency tests were. No GPU/CUDA requirement on Apple Silicon.
When phase 21 begins, create a separate training venv and a reviewed pinned optional
manifest first. Install Homebrew `libomp` for the LightGBM macOS build path where needed;
do not invent an already-existing forecast training command.
[Official macOS installation guidance](https://lightgbm.readthedocs.io/en/stable/Installation-Guide.html).
