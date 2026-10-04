# CartPilot functional acceptance audit

Date: 3 October 2026. Scope: current repository and isolated local regression. No real credentials, external writes or user database were used. This audit does not implement missing product features.

Statuses: IMPLEMENTED = source exists; PASS LOCAL = exercised by regression; MISSING = no feature to execute; NOT RUN = requires separate environment/tooling. Historical browser evidence is not a fresh browser test.

## Current review — 4 October 2026

The tables below describe the historical 3 October baseline. Phase 15 supersedes its
missing authentication, product CRUD, sales import and revenue-summary entries.
Use [the nine-step testing guide](STEP_BY_STEP_TESTING.md) for the current assessment,
commands, evidence limits and remaining gaps. Use [the manual test sheet](MANUAL_TEST_CASES.csv)
in Excel; its results are deliberately unfilled until someone executes each case.

## 1. Basic functionality checklist

| Feature / test | Status | Evidence or prerequisite |
| --- | --- | --- |
| Signup, login, logout | MISSING | No identity API or account UI; Merchant is store identity, not a login |
| Unauthenticated request denied | MISSING | No authenticated principal; read APIs accept unauthenticated requests |
| Wrong password, token expiry, session revocation | MISSING | Requires identity/session implementation |
| Cross-merchant ownership validation | PASS LOCAL | store, specialist, actions and release-hardening tests; scope validation is not authentication |
| Dashboard data/error/empty states | PASS LOCAL | frontend/tests/Dashboard.test.tsx and store API regressions |
| Add, edit, delete/archive product | MISSING | GET catalog exists; no general CRUD API/UI |
| CSV product/sales upload | MISSING | Seed fixtures and Shopify read-only sync are not user uploads |
| Pricing/restock/promotion/listing recommendations | PASS LOCAL | Specialist rule/API tests; deterministic heuristics |
| Merchant-goal coordination | PASS LOCAL | test_cross_agent.py, test_orchestrator.py and frontend CrossAgent tests |
| Human approval/confirmed local execution/audit | PASS LOCAL | test_actions*.py and frontend Actions.test.tsx |
| Real supplier orders/promotion launches | MISSING | Existing executors record simulations |
| Product/order/history persistence | PASS LOCAL | ORM, migration, bootstrap and guarded workflow tests |
| Account records | MISSING | No User/auth entity |
| Saved recommendation history | PASS LOCAL | explicit persistence and scoped read tests; analysis alone is not automatic saving |
| Persistent analytics snapshots | MISSING | Signals are computed from store records, not saved analytics snapshots |
| API responses and invalid inputs | PASS LOCAL | store/specialist/orchestration/action tests |
| Email/in-app notification delivery | MISSING | No notification API/provider/UI |
| Mobile layout | IMPLEMENTED; FRESH BROWSER NOT RUN | Historical Phase 14 widths 1440/768/390; unit tests do not prove current visual layout |

## 2. Main merchant scenarios

### New merchant: account → five products → analysis

- [ ] Create account: BLOCKED by missing authentication/onboarding.
- [ ] Add five products through UI: BLOCKED by missing product CRUD.
- [ ] Analyze no-sales products: existing fixtures verify insufficient-data handling; no sales must not be represented as measured revenue growth.
- [ ] Revenue insights: scoped sales/catalog signals exist; attributable revenue uplift is not measured.
- [ ] Refresh and retain product data: needs CRUD before this exact UI workflow can execute.

The complete scenario is BLOCKED, not passed by directly inserting fixture records. Existing regression uses fixtures for analysis only.

### Existing merchant: sales upload → analysis → suggested actions

- [ ] Upload sales CSV: BLOCKED by missing import workflow.
- [x] Analyze fixture sales and stock: backend regression exercises seeded order history.
- [x] Detect stockout/excess/declining-sales/listing opportunities: cross-agent regression.
- [ ] Explicit top/bottom seller ranking UI: not a dedicated ranking feature; sales values are available in catalog data.
- [x] Generate structured suggestions and explain conflicts: cross-agent regression.
- [ ] Demonstrate real revenue increase: requires real evaluation; not established by suggestions.

## 3. API checklist: use actual routes

All business routes start /api/v1. Explore /docs. A generic POST /recommendation or GET /analytics is not implemented.

| Request | Expected behavior |
| --- | --- |
| GET /health | 200 liveness |
| GET /api/v1/health/detailed | 200 diagnostics; inspect database status |
| GET /api/v1/merchants | 200 store summaries |
| GET /api/v1/products?merchant_id=ID | 200 paginated catalog for known merchant |
| POST /api/v1/products | Not implemented; 405 is not a working upload feature |
| GET /api/v1/inventory?merchant_id=ID | 200 inventory |
| POST /api/v1/{pricing,restock,promotion,listing}/recommend | 200 valid supported input; 422 invalid; 403 foreign scope; 404 unknown product |
| POST /api/v1/orchestrate | 200 valid scoped goal; errors for invalid scope/input |
| GET /api/v1/recommendations?merchant_id=ID | 200 explicitly saved history |
| GET /api/v1/actions; /action-history | 200 valid scope |
| POST /api/v1/actions and review/execute routes | Local guarded workflow; production 403 |
| Shopify status/last-sync/sync | Local read-only integration; production 403; mocked transport regression |

Do not expect 200 for every test. Invalid inputs must fail with intentional 4xx; sanitized unavailable-storage failures use 503. Full route catalog: docs/API_DATABASE_SECURITY.md.

## 4. Logs and error checks

- [x] Isolated regression checks sanitized storage/unknown errors and rollback.
- [x] Frontend tests exercise loading, empty and API-error states.
- [ ] Fresh browser Console/Network inspection: NOT RUN in this audit.
- [ ] Actual deployment logs and serverless timeouts: NOT RUN; no deployed URL supplied.
- [ ] Verify no credentials in logs: examine provider logs privately, do not paste raw URLs/tokens.

## 5. Thirty recommendation acceptance cases

Use fixed fixtures and explicit expected predicates, not subjective “looks good”. Existing tests cover many of these behaviors; this list is a manual acceptance specification, not a claimed separately executed 30-case experiment.

| # | Input / condition | Expected result |
| --- | --- | --- |
| 1 | Strong demand + low stock | Restock priority; demand-stimulating promotion suppressed |
| 2 | Mouse 8 available, velocity 5/day | Coverage 1.6 days; fixture restock 67 |
| 3 | Safe Mouse price 999 | Proposed 1048.95 under default fixture settings |
| 4 | Weak demand + excess safe stock | Consider margin-safe promotion |
| 5 | Speaker declining fixture sales | 10% candidate, 1349.10 |
| 6 | Unknown cost | Block unsafe price/discount proposals |
| 7 | Requested price below floor | Clamp or reject according to movement/floor conflict |
| 8 | Proposed 50% price increase | Fail default 10% action policy |
| 9 | Promotion violates retained margin | Reduce discount or no candidate |
| 10 | Zero sales + inadequate history | Insufficient-data handling; no confident prediction |
| 11 | Cancelled orders in lookback | Excluded from demand |
| 12 | Orders outside lookback | Excluded |
| 13 | Reserved/unavailable units | Excluded from available stock |
| 14 | Negative derived stock | Available quantity floored at zero |
| 15 | Zero velocity | No invented stockout date |
| 16 | Reorder quantity above cap | Cap and expose risk |
| 17 | Inactive product | No executable candidate |
| 18 | Missing inventory | Do not treat as safe surplus |
| 19 | Missing description | Listing issue and grounded review |
| 20 | Missing verified attributes | Request verification; invent no product facts |
| 21 | Healthy listing | Avoid unnecessary urgent listing action |
| 22 | Price decrease and discount overlap | Resolve/defer competing proposals |
| 23 | Poor listing + discount candidate | Listing dependency visible |
| 24 | Changed price after approval | Execution blocked as stale |
| 25 | Changed cost after approval | Execution blocked as stale/unsafe |
| 26 | New stockout before promotion execution | Execution blocked |
| 27 | Repeat successful execution | Idempotent result, no second mutation |
| 28 | Foreign merchant product | 403; no cross-store results |
| 29 | Specialist failure | Partial-result warnings and safety blocks |
| 30 | Queue/action budget exceeded | Visible omissions; critical inventory retained |

Cart abandonment and conversion campaigns are OUT OF SCOPE: no cart/funnel events or recovery agent. Add those requirements/data before evaluating them.

For a separately executed labeled benchmark, report rule-conformance rate = passed supported cases / executed supported cases × 100, with fixtures, assertions and excluded cases recorded. Do not call this forecasting accuracy or measured business performance.

## 6. Database verification

- [x] ORM constraints/migrations and seed/reseed tested with disposable fixtures.
- [x] Local price/listing changes and workflow audit persistence tested.
- [x] Recommendations are saved only through explicit persistence paths.
- [ ] UI product add → refresh: missing CRUD.
- [ ] User/session rows: missing auth.
- [ ] Deployed Neon persistence/restore: NOT RUN; provider access/target needed.

Never test by deleting/resetting a valuable store database.

## 7. Load and performance

Targets supplied by user: API <2 seconds, page <3 seconds. Define percentile, concurrency, dataset and hardware before calling these passed.

- [ ] Multi-user k6/Locust/JMeter test: NOT RUN.
- [ ] p50/p95 latency, error rate and throughput under concurrency: NOT RUN.
- [ ] Deployed cold starts/Neon connection limits: NOT RUN.
- Historical release-performance.json has only three sequential ASGI samples, not a load test; do not use it as proof of multi-user capacity.

## 8. Security

Authentication/session/admin tests are BLOCKED by missing features. No /admin or /admin/users exists; a 404 does not prove admin authorization. Existing merchant scope and action policy tests pass locally but do not secure unauthenticated public users.

## 9. Lighthouse

- [ ] Desktop/mobile performance >80: NOT RUN.
- [ ] Accessibility >90: NOT RUN.
- [ ] SEO/best-practices scores: NOT RUN.

Run against a production frontend artifact, record URL/browser/version/device profile and retain JSON/HTML results. Historical responsive evidence and unit tests are not Lighthouse scores.

## Implementation dependencies

1. Identity, secure sessions, server-bound merchant authorization for every protected API.
2. Scoped product CRUD/archive and validated inventory edits.
3. Sales import with format preview, validation and idempotency.
4. New-store/onboarding and explicit seller-ranking/revenue summaries.
5. Authenticated guarded hosted workflow; keep external execution simulated until integrated.
6. In-app notifications, then provider-configured email.
7. Complete two user journeys, browser accessibility audit and isolated load test.

Do not bypass production gates or add unsupported endpoints only to make a checklist green. Feature development is separate from this testing audit.

## Executed audit results

- Initial backend run: 563 passed, 1 failed in 18.75 seconds. Existing health CORS test inherited the developer .env CORS setting.
- Fix: tests/conftest.py now supplies explicit test CORS origins and pooled mode before importing app. Developer .env unchanged.
- Backend rerun: **564 passed in 16.24 seconds**.
- Frontend: **76 passed across 9 files**; **TypeScript/Vite build passed**.
- git diff whitespace check: passed.
- No new browser walkthrough, Lighthouse, multi-user load test or cloud log inspection was executed in this audit. No feature-development completion is claimed.

## Subsequent implementation update

The user requested feature development after this audit. Its missing-feature table above
is the original baseline, not the current account/store implementation. New local account,
CRUD/archive, sales import, ranking and on-demand alert work is documented in
../ACCOUNT_STORE_MANAGEMENT.md and ../../phases/PHASE_15.md. Production routes now enforce
account authentication. Email delivery, recovery/verification and external execution are
still missing. Browser/load/Lighthouse results have not been fabricated.
