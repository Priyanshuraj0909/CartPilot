# CartPilot upgrade master plan

Status: audit/planning complete; platform implementation has not started.
Baseline: Phase 18, commit `7d19283`. Evidence: [repository audit](REPOSITORY_AUDIT.md).
User intent: production-oriented, explainable commerce intelligence, built incrementally
on React/TypeScript, FastAPI, PostgreSQL, SQLAlchemy and Alembic.

## Scope and non-negotiable boundaries

Preserve accounts, catalog/sales imports, specialists, existing approvals, storefront,
chat, recovery, test payments/refunds, Shopify reads and MCP contracts. Upgrade in place
using additive migrations and feature flags; never relabel a planned feature as delivered.
This publication contains audit/planning/documentation only and uses the existing
deployment automation. No feature/schema/provider setting changes or live payments.

The user's requested "do not start Phase 18 until audit and plan are complete" is
interpreted against the actual repository: historical Phase 18 remains intact. The
new dependency-ordered phases are 19–27. Completing this plan clears the planning
prerequisite; it does not mean all nine implementation phases are complete.

LLMs may emit bounded typed suggestions. Application services alone check identity,
merchant scope, current inventory/prices/policy, explicit approval and a separate
confirmation. Models, MCP, scheduler and workflow framework never authorize payments,
refunds, catalog price changes, promotions or supplier orders. Live payment enablement
requires a separate explicit user decision, regardless of future model results.

## Dependency order and phase gates

| Phase | Deliverable | Must follow | Release gate |
| --- | --- | --- | --- |
| 19 | Persistent-cart evolution and safe inventory leases; initial security remediation | Audit/planning | Last-unit contention, expiry/release and crash rollback pass in PostgreSQL; compatible legacy carts; dependency findings addressed or explicitly assessed |
| 20 | Complete test-order lifecycle, webhook inbox/outbox, idempotent reconciliation, provenance/events | 19 | Duplicate/out-of-order delivery and crash recovery create one order and consume/release once; simulation remains excluded from real sales |
| 21 | Time-aware demand baselines, LightGBM candidate, XGBoost comparison when warranted, MLflow runs | 20 data contracts | Versioned as-of dataset, untouched test period, baseline comparison, uncertainty/cold-start/latency reports; fallback retained if candidate fails |
| 22 | Unified hybrid retrieval, consenting session personalization, exposure logging and LTR | 20; use 21 experiment conventions | Candidate recall + temporal query-group ranking evaluation, leakage/bias checks, tenant isolation, baseline fallback |
| 23 | Durable specialist workflow with human review/resume | 20; current specialists retained | Kill/restart/replay, stale approval, partial failure and idempotent tool tests; no model authorization path |
| 24 | Validated image assets and multimodal retrieval | 22 retrieval/version contracts | Malicious/large-image rejection, tenant-safe search, labeled retrieval/latency evaluation, text fallback |
| 25 | Forecast-informed replenishment and price-review scenarios | 21, 23; optional 22 context | Feasible bounded scenarios, unknown-cost/elasticity safeguards, no automatic actuation, timeout/infeasible fallback |
| 26 | Merchant intelligence and explanation dashboard | 21–25 read APIs; existing analytics retained | Provenance/sample size/freshness/uncertainty shown; accessible review/confirmation; mobile/error/empty-state checks |
| 27 | Deployment, observability, security and model-monitoring release qualification | All relevant phases | Restore drill, load/SLO report, dependency/tenant review, rollback exercise, worker/model health and alert checks |

Security, telemetry and test work accompany every phase; phase 27 is qualification,
not permission to postpone protection until the end. Forecasting can remain baseline-only
when real history is insufficient. LTR cannot ship as trained personalization until
exposure/label data exists. No fabricated forecasts or evaluation claims to fill gaps.

## Architecture decisions

Keep one modular backend and existing frontend. PostgreSQL remains authoritative for
business state, leases, idempotency, events and approvals. Start with one optional
persistent worker process using the same codebase and database; no service split needed.

| Candidate | Decision at audit | Evidence required before adding |
| --- | --- | --- |
| LightGBM / XGBoost | Offline CPU experiments; select one production artifact initially | Forecast baselines, dataset adequacy and measured validation/latency; XGBoost may also supply query-group LTR |
| MLflow | Planned for phase 21, isolated training environment | Versioned experiment tracking is missing; local SQLite metadata/artifacts first, authenticated shared setup only when required |
| pgvector | Defer until phase 22/24 benchmark | Current catalog cap 500 and JSON vectors work at demo scale; tenant-filtered exact PostgreSQL vector search must justify migration; ANN only after measured need |
| LangGraph | Evaluate in phase 23, not a mandatory rewrite | Demonstrate that branching/checkpoints/interrupts beat a typed SQL workflow; persist checkpoints in Postgres and enforce existing tools outside graph reasoning |
| Redis | Keep optional; no new correctness dependency | Add only for measured cache/queue need, defined invalidation and failure policy; never sole inventory/payment/approval record |
| OR-Tools | Defer to phase 25 | Shared budget/MOQ/capacity constraints that simple bounded heuristics cannot satisfy; test solver feasibility/timeouts and compare baseline |

Details, invariants, source references and contracts: [architecture](UPGRADE_ARCHITECTURE.md).

## Per-phase delivery protocol

1. Record problem, code evidence, risks, affected paths and smallest design in the phase document.
2. Add migration preflight/compatibility and rollback strategy before schema changes.
3. Implement typed backend/domain changes and required frontend states; preserve old behavior behind defaults.
4. Cover happy, invalid, boundary and failure cases; use PostgreSQL for locking claims and a real browser for changed workflows.
5. Run relevant regressions and production build; record exact pass/fail/skips and unverified conditions.
6. Update README, architecture/status/test records and [progress](UPGRADE_PROGRESS.md).
7. Make small `feat:`, `fix:`, `test:`, `refactor:` or `docs:` commits; suggested messages are in the roadmap.
8. Apply tested additive migrations before rollout, verify GitHub CI/deployment and read-only smoke probes; disable feature on failure and preserve evidence.

Do not backfill hosted sample data, download model weights into serverless functions,
alter source inventory from test payments or enable external write APIs as a side effect.

## Success criteria

Commerce correctness means no double allocation, duplicate order or over-refund under
tested retries/crashes, with reconstructible events and visible unknown states. ML
success means reproducible out-of-time performance against a baseline, documented
uncertainty and serving cost, not an assumed percentage improvement. Product success
means merchants can inspect evidence and control sensitive actions. Production readiness
also needs measured operating limits, response ownership, backups and rollback evidence.
