# CartPilot upgrade test strategy

Status: strategy plus verified baseline, not evidence that planned features pass.
Every feature needs happy-path, invalid-input, boundary and failure tests under AGENTS.md.
Run meaningful checks for the changed boundary; do not infer coverage from test counts.

## Fresh audit baseline

23 October 2026: backend **738 passed / 5 opt-in skipped** in 39.78s; frontend
**174 passed / 21 files**; TypeScript/Vite build passed. Separately, all **5 PostgreSQL
concurrency tests passed** in 0.45s on PostgreSQL 17.11. `pip check` passed.
Security audits found **13 npm package entries** (2 critical/6 high/5 moderate),
**zero production-only npm findings**, and **two Python advisories**. These are open
findings, not passing security gates. See [audit evidence](REPOSITORY_AUDIT.md).

The initial PostgreSQL startup attempted occupied port 5432; resulting five connection
setup errors were infrastructure failures. Starting the task-owned cluster explicitly
on 55439 resolved them; no application change or hosted database access was involved.
Fresh browser/load/model/provider tests were not run for this docs-only audit.

## Verification layers

| Layer | Coverage and required failure assertions |
| --- | --- |
| Pure domain tests | Money/quantity/date boundaries, status transitions, policy/permissions, model feature availability and deterministic fallback |
| API contracts | Pydantic rejects unknown/untrusted fields, tenant/product mismatch, missing/expired capability, boolean confirmation bypass, oversize/malformed data and provider failures |
| PostgreSQL integration | Real row locks/uniqueness/transaction rollback under contention; SQLite cannot establish these semantics |
| Migration tests | Upgrade from existing populated head, legacy/synthetic provenance, constraints preflight, re-upgrade, compatible app rollout; downgrade only on disposable data |
| Frontend | Loading/error/empty/stale/partial states, typed response handling, merchant switching, accessibility, review/confirmation separation and unknown payment retries |
| Browser | Real desktop/mobile shopping and merchant scenarios with isolated synthetic data; no mock browser report relabeled as hosted UAT |
| Data/model | Temporal split/feature availability, manifests, leakage/censoring tests, baseline/candidate metrics, cold start, reproducibility, inference latency and fallback |
| Operations | Signed delivery/replay/crash injection, worker reclaim, load/outage, dependency scans, deploy/rollback, backup restore and model monitoring |

## Phase-specific acceptance matrix

| Phase | Happy | Invalid | Boundary | Failure / concurrency |
| --- | --- | --- | --- | --- |
| 19 | Approve, allocate, release/expire | Wrong merchant/product; changed quote | Last unit, exact expiry, all stock source-reserved | Two carts/last unit; multi-product deadlock order; worker crash; repeated release; source sync race |
| 20 | Test payment → one test order | Invalid signature/reference/amount/currency | Exact refund balance; partial return | Duplicate/reordered webhook; provider accepted/DB failed; paid/cancel race; stale claims; order/stock effect once |
| 21 | Reproducible baseline/forecast run | Missing schema/version/tenant | Zero demand, short history, horizon overlap | Late data; stockout censoring; corrupted artifact; unavailable model; deterministic fallback |
| 22 | Shared search/preview, mature labels | Cross-tenant event/profile/candidate | New user/SKU, empty candidate set | Stale index; provider timeout; label-window overlap; source exposure bias and grouped evaluation |
| 23 | Pause/review/resume | Model tries to approve/execute | Expired lease, changed approval version | Kill at every side effect; duplicate resume; failed specialist; partial graph and stale current state |
| 24 | Image → eligible catalog matches | Spoofed MIME, malformed bytes, private URLs | Byte/pixel/dimension limits | Decoder/resource exhaustion; missing/deleted asset; unavailable encoder and text fallback |
| 25 | Feasible bounded scenario | Unknown cost/unsupported elasticity | MOQ/cap/budget/cent rounding | Infeasible/time-limited solver; stale forecast; changed inventory; preserve baseline recommendation |
| 26 | Inspect evidence/review action | Invalid filters/scopes | Empty/large/partial datasets | Broken read API; stale model; mobile overflow; keyboard/focus; no false revenue/accuracy statement |
| 27 | Monitor and roll back | Invalid roles/egress/oversize headers | Defined load and queue capacity | DB/provider loss; worker death; stale/drifting model; restore and alert delivery |

Security tests must cover both merchant boundaries and shopper ownership, including
indirect identifiers in event/job/checkpoint/model/image references. Do not target
production with destructive tests or seed it for convenience.

## ML evaluation protocol

Freeze dataset/feature/label contracts and eligibility before fitting. Preserve event
time and arrival time. Aggregate daily units in a declared store timezone; distinguish
observed zero demand from missing/closed/stockout-censored days. Exclude simulation,
test payments and seeded fixtures from merchant-quality claims. Record inclusion counts.

Use chronological train → validation → final test windows, with rolling-origin folds
within development data. Purge rows whose target horizon crosses a fold boundary and
apply gaps matching feature/label windows. Fit preprocessing only on training data.
Global models still split on common time boundaries; never leak a later product/time
row into an earlier fold. Freeze hyperparameters, baseline selection and promotion
criteria before opening the final test set. Time-aware splitting prevents future-data
training, but feature/label design still needs its own leakage checks.
[TimeSeriesSplit reference](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html).

Forecast evaluation compares seasonal naive, moving average and intermittent baselines
to the candidate using identical horizons/data. Report MAE, WAPE (undefined for zero
aggregate actual demand), MASE (undefined when scaling baseline variation is zero),
pinball loss and interval coverage/width; avoid MAPE on zeros. Report product/category,
volume and cold-start cohorts, stockout bias, sample sizes and unavailable metrics.
Quantile or residual interval calibration uses held-out validation, never the test set.

Recommendation evaluation measures eligible-candidate Recall@K before rank quality,
then grouped NDCG@K/MRR and catalog/coverage/cold-start metrics. Keep one query/session
group within a split, wait for labels to mature and use only as-of features. Do not call
unexposed items observed negative outcomes or report offline lift as incremental revenue.
Only a consented, correctly randomized experiment can assess causal business impact.

Each run tracks dataset hash/version, git/feature version, model/encoder version,
parameters/seed, time boundaries, metrics with cohort counts, artifact hash/format,
hardware and warm/cold inference p50/p95, throughput and memory. Use local MLflow during
phase 21; export readable evaluation reports for review. Trust and pin model artifacts;
never load arbitrary user-uploaded pickle/model code.

Promotion requires correctness and tenant tests, a predeclared useful comparison with
the strongest appropriate baseline, acceptable cohort behavior/uncertainty and measured
latency/resource limits. If insufficient data or no demonstrated advantage, retain the
baseline. No target accuracy or business gain is claimed in advance. Model rollback
must switch an approved immutable version without retraining or database rollback.

## Performance and resilience targets

Proposed initial budgets, to be benchmarked and adjusted in phase plans: warm model-only
forecast inference p95 <=100ms per product; ranking model p95 <=200ms for a bounded
candidate set; API-only cached/local search p95 <=500ms at a declared local load.
These are design targets, not measured current performance or hosted SLOs. External
provider latency, cold starts, batching size, data size and concurrency must be reported
separately. Do not hide an upstream 8–12 second timeout in an aggregate local benchmark.

Record throughput, error/timeout/fallback rates, DB query counts/pool pressure, queue
age and lease conflicts. Load tests use realistic tenant skew and resource limits.
Crash tests inject before/after provider calls and transaction commits. Readiness must
account for DB/migrations/model freshness and actual worker heartbeat; liveness alone
cannot qualify a release. Restore into an isolated database and verify financial/event
invariants before claiming backups work.

## Exact current commands on Apple Silicon

From repository root (existing virtualenv and node_modules):

```bash
(cd backend && venv/bin/python -m pytest -q)
(cd frontend && npm run test:run && npm run build)
backend/venv/bin/python -m pip check
(cd frontend && npm audit && npm audit --omit=dev)
git diff --check
```

The first npm audit currently exits 1, so the shell `&&` stops before production-only
audit. Run `cd frontend && npm audit --omit=dev` separately to reproduce its zero result.
Do not treat either advisory scan as exhaustive exploitability analysis. Python audit
tooling can live in a disposable venv without adding runtime requirements:

```bash
backend/venv/bin/python -m venv /private/tmp/cartpilot-upgrade-audit-tools
/private/tmp/cartpilot-upgrade-audit-tools/bin/python -m pip install pip-audit
/private/tmp/cartpilot-upgrade-audit-tools/bin/python -m pip_audit \
  -r backend/requirements.lock.txt --no-deps --disable-pip
```

For isolated PostgreSQL tests, use an available port and a NEW task-owned directory.
The test fixture deletes all rows in the exact database `cartpilot_ci`; never use it
for valuable data. No developer `.env` database URL is used by this recipe:

```bash
export PATH="/opt/homebrew/opt/postgresql@17/bin:$PATH"
CP_TEST_PG_DIR=$(mktemp -d /private/tmp/cartpilot-upgrade-pg.XXXXXX)
initdb -D "$CP_TEST_PG_DIR/data" -U cartpilot_ci -A trust
pg_ctl -D "$CP_TEST_PG_DIR/data" -l "$CP_TEST_PG_DIR/server.log" \
  -o "-h 127.0.0.1 -p 55439 -k $CP_TEST_PG_DIR" start
createdb -h 127.0.0.1 -p 55439 -U cartpilot_ci cartpilot_ci
cd backend
ENVIRONMENT=test REDIS_URL='' \
  DATABASE_URL=postgresql+asyncpg://cartpilot_ci@127.0.0.1:55439/cartpilot_ci \
  venv/bin/python -m alembic upgrade head
CARTPILOT_TEST_POSTGRES_URL=postgresql+asyncpg://cartpilot_ci@127.0.0.1:55439/cartpilot_ci \
  venv/bin/python -m pytest tests/test_postgres_integration.py -q
pg_ctl -D "$CP_TEST_PG_DIR/data" stop -m fast
```

Do not proceed with tests if cluster startup or migration fails. Stop the task-owned
cluster even after test failure; never stop a process merely because it occupies a port.
Provider/live-model tests remain opt-in with synthetic fixtures and explicit test keys.
CI currently runs backend/frontend/PG jobs; adding browser/security/ML gates is planned,
not an already configured workflow claim.
