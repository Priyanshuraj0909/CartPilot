# CARTPILOT MASTER PLAN

## Phase 1 — Foundation

Goal:

Create the project structure and development environment.

Deliverables:

- Git repository
- FastAPI backend
- React frontend
- PostgreSQL
- Docker Compose
- environment configuration
- health check
- basic CI/testing

---

## Phase 2 — Data Layer

Build:

- Product model
- Inventory model
- Order model
- Merchant model
- Price history
- Action log

Create mock store data.

---

## Phase 3 — Pricing Agent

Status: COMPLETE. Deterministic recommendation-only agent, validated API,
configurable guardrails, optional pending persistence service, and regression tests.
Actual product prices are never automatically changed. See `phases/PHASE_03.md`
for pricing signals, confidence/risk formulas, configuration, and verification.

Build:

Pricing Agent

Input:

- product
- current price
- sales velocity
- inventory
- historical data

Output:

Structured pricing recommendation.

Example:

{
  "product_id": "SKU-001",
  "current_price": 999,
  "recommended_price": 1049,
  "reason": "High sales velocity and low inventory",
  "confidence": 0.86,
  "risk_level": "medium"
}

---

## Phase 4 — Restock Agent

Status: COMPLETE. Independently callable deterministic Restock Agent, typed API,
configurable lead time/safety stock/quantity cap, optional pending persistence, and
regression tests. No purchase orders or automatic inventory changes.
See `phases/PHASE_04.md` for formulas, policies, and verification.

Build:

Restock Agent.

Detect:

- low inventory
- high sales velocity
- potential stockout

Produce:

- recommended reorder quantity
- estimated stockout date
- reason
- confidence

---

## Phase 5 — Master Orchestrator

Status: COMPLETE. Deterministic goal routing, merchant-scoped shared business context,
Pricing/Restock coordination, conflict deferral, priority ordering, partial failures,
and typed advisory API. No execution or automatic approval.
See `phases/PHASE_05.md` and `docs/examples/orchestration-demo.json`.

Implement:

Sense
↓
Context
↓
Agent selection
↓
Parallel agent execution
↓
Conflict resolution
↓
Policy validation
↓
Action plan

---

## Phase 6 — Frontend

Status: COMPLETE. Six live-data pages, typed API client, reusable recommendation
cards and product drawer, merchant-scoped read APIs, accessible responsive layouts,
and tested loading/error/empty states. Advisory analysis only; approvals and action
history remain future work. See `phases/PHASE_06.md` for verification and limitations.

---

## Phase 7 — Promotion Agent

Status: COMPLETE. Deterministic slow-mover/excess-stock detection, windowed sales trend,
Decimal discounts, retained gross-margin and stockout protection, advisory API,
optional pending persistence, orchestration routing/conflicts, and frontend cards.
See `phases/PHASE_07.md` and `docs/examples/promotion-demo.json`. No promotions execute.

Detect:

- slow movers
- declining sales
- promotional opportunities

Recommend:

- discount
- campaign
- target products

---

## Phase 8 — Listing Agent

Status: COMPLETE. Deterministic listing quality checks, grounded content suggestions,
typed advisory API, optional pending persistence, listing-only and combined routes,
cross-agent synergies, current/proposed frontend comparisons, and five active agents.
See `phases/PHASE_08.md` and `docs/examples/listing-demo.json`. No listings publish.

Analyze:

- title
- description
- attributes
- SEO metadata

Produce listing improvement recommendations.

---

## Phase 9 — Guarded Actions

Status: COMPLETE. Typed action conversion, policy checks, human approval/rejection,
separate confirmed execution, current-state revalidation, deduplication, transaction
rollback, merchant scope and persistent auditing. Approvals and Action History UI.
Prices and listings mutate local data; restock and promotion execute simulations.
Agents remain recommendation-only. See `phases/PHASE_09.md`. Phase 10 extends advisory planning through this guarded boundary.

Introduce:

- approval system
- action policies
- price limits
- discount limits
- inventory limits
- audit logs

Allow approved simulated actions.

---

## Phase 10 — Cross-Agent Intelligence

Status: COMPLETE. Six controlled merchant goals, fresh opportunity detection,
per-product specialist selection, structured conflicts/synergies/dependencies,
goal weights and deterministic priority, hard inventory overrides, bounded store
analysis/action queues with critical overflow visibility, partial failures, and
an enhanced AI Manager summary/priority queue. Plan candidates enter Phase 9 approval
without execution. See `phases/PHASE_10.md` and `docs/examples/cross-agent-demo.json`.
Phase 10 adds no external commerce integration or unattended execution. Phase 11 read-only integration is documented below.

Implement:

Pricing
+
Restock
+
Promotion
+
Listing

under the Master Orchestrator.

Resolve conflicts.

Create unified merchant goal execution.

---

## Phase 11 — Real E-Commerce Integration

After the mock system is stable:

Add Shopify integration.

Use read-only access first.

Then guarded write operations.

---

## Phase 12 — Final Testing

Perform:

- unit testing
- integration testing
- API testing
- agent testing
- frontend testing
- security testing
- failure testing
- end-to-end testing
### Phase 11 implementation status

**COMPLETE (code and mocked verification)**: environment-only credentials; supported
centralized API version; closed read-only GraphQL client; merchant/store identity;
idempotent variant/product, multi-location inventory and recent-order sync; external
mapping metadata; safe unknown-cost handling; pagination, bounded retries, partial
failures and last summary; development-only APIs; Integrations UI; agent/orchestrator
compatibility; migration, tests and offline demo. Seeded local data is retained.

See [Phase 11](phases/PHASE_11.md) for setup and limits. Live store verification requires
credentials. No Shopify writes or Phase 12 functionality has been implemented.

### Phase 12 — final release verification

**COMPLETE. READY WITH MINOR LIMITATIONS for a trusted local demo/submission.**
542 backend tests, 71 frontend tests and TypeScript/Vite build passed. Clean SQLite
migrations/seed/HTTP workflow, exhaustive state transitions, ownership/failure/logging
hardening, real Chrome nine-page/approval/Shopify walkthrough, source-copy reproduction
and basic performance were verified. No major feature or external write was added.

The [Phase 12 matrix](phases/PHASE_12.md) records PASS/NOT VERIFIED/limitations separately.
Docker, live PostgreSQL and real Shopify remain unverified; public deployment requires
authenticated merchant identity and further infrastructure/dependency hardening.
Phase 13 follows with deployment configuration; no autonomous execution or Shopify write access is enabled.

### Phase 13 — deployment and production-style setup

Deployment configuration, separate release/start commands, centralized validated
settings, static-build API configuration/SPA routing, optional Redis, deployment
guide and minimal CI. Existing safety gates remain intact. See
[Phase 13](phases/PHASE_13.md) for verification and hosting limitations. No Phase 14
features, public authentication, external writes or new agents are introduced.

### Phase 14 — final demo, viva and submission

Documentation, source-matched formulas/agent guide, seven-minute four-product demo,
unsafe-policy fixture, 52 viva Q&A, report/12-slide content outline, 15 real screenshots,
final 560/76 tests/build/bootstrap/browser verification and secret-safe source archive.
No product feature or new API/agent/integration is added. See
[Phase 14](phases/PHASE_14.md) and [Final status](FINAL_STATUS.md).
Stop development after this phase unless a real defect or guide request requires it.

### Phase 15 — explicitly requested merchant workflow improvements

Account/session authorization, catalog CRUD/archive, sales import, observed-sales
summaries and in-app stock alerts. See phases/PHASE_15.md and
[setup/limits](docs/ACCOUNT_STORE_MANAGEMENT.md). Historical Phase 14 evidence is retained.
