# Current test evidence — complete commerce workflows

Verified 23 October 2026 (Asia/Kolkata). Phase 18 supersedes earlier current counts.

| Check | Result |
| --- | --- |
| Backend `venv/bin/python -m pytest -q` | **738 passed**, five opt-in PostgreSQL checks skipped; 36.58 seconds |
| Frontend `npm run test:run` | **174 passed**, 21 files |
| Frontend `npm run build` | TypeScript and Vite production build passed |
| Disposable PostgreSQL | Migrations through `18_commerce_workflows`; five concurrency tests passed, including refund caps and single-draft recovery acceptance |
| SQLite migration | Existing Phase 17 shopper/cart records survive upgrade/downgrade; prior migration tests pass |
| Real Chrome | Multi-item chat, recovery discount, separate approval/simulation, partial refund, return review, reload restoration and merchant ranking/ledger passed; 390px without horizontal overflow; no captured runtime exceptions |
| Hosted migration | `17_commerce` → `18_commerce_workflows`; all existing row counts preserved |
| Provider paths | Structured failover, optional embedding backend, weather failure, refund processing/reconciliation and ambiguous outcomes exercised with mocks |
| Worker | Due claims, scheduling and recoverable tick failures tested; persistent hosting not provisioned |
| Live providers / payments / external MCP clients | Not verified; no live charges or fulfillment implemented |

Evidence: [browser](docs/examples/commerce-workflows-browser.json),
[migration](docs/examples/commerce-workflows-migration.json),
[parity guide](docs/COMMERCE_PARITY.md), [screenshots](docs/screenshots/README.md).
No measured incremental revenue is inferred. Remote release results are in FINAL_STATUS.md.

---

## Historical reliability release evidence

# Reliability release — 21 October 2026

Verified 21 October 2026 (Asia/Kolkata). Current source supersedes the historical Phase
14 counts below. Production deployment results are maintained in FINAL_STATUS.md.

| Check | Result |
| --- | --- |
| Backend: venv/bin/python -m pytest -q | 635 passed; 2 opt-in PostgreSQL tests skipped |
| Frontend: npm run test:run | 146 passed across 17 files |
| Frontend: npm run build | TypeScript and Vite production build passed |
| Disposable PostgreSQL | All migrations through 16_reliability; 2 concurrency tests passed |
| SQLite migration | Upgrade/downgrade preserves legacy activity and linked recommendations |
| Added regression scope | Rate budgets/expiry/spoofed headers/storage failure; history ownership/pagination/partial results; recovery rollback/session revocation; Shopify cached credentials/retry limits; worker lifecycle; activity UI states |
| Live Shopify, worker hosting and production load | Not verified by these tests |
| Remote CI | Backend, frontend and PostgreSQL jobs passed for release 90a47de |
| Hosted HTTP checks | Frontend bundle, same-origin database health/authentication/new route and SPA route passed; direct backend-hostname probes failed from this environment |
| Lint | Not configured |

Commands and database isolation requirements are in docs/RELIABILITY_RELEASE.md.
The PostgreSQL checks are targeted integration tests, not a load/stress benchmark.

---

## Historical Phase 14 evidence (3 October 2026)

# Final test evidence — Phase 14

Verified 3 October 2026 (Asia/Kolkata). Results come from this repository's actual runs,
not an assumed Antigravity report. Commands below reproduce the applicable checks.

| Check | Exact result / scope |
| --- | --- |
| Backend `venv/bin/python -m pytest -q` from backend | **560 passed**, 18.49 s final Phase 14 run |
| Frontend `npm run test:run` | **76 passed**, 9 files, 2.39 s |
| Frontend `VITE_API_URL=https://api.example.test npm run build` | PASS; tsc + Vite 5.4.21, 1.02 s Vite build |
| Lint | NOT CONFIGURED; no fabricated lint pass |
| Clean migration | PASS; new disposable SQLite, all 3 Alembic revisions to 11shopify_read_only |
| Standard seed command | PASS; explicit isolated seed and repeat skip; 1 merchant, 25 products/inventory/history, 110 orders before fixtures |
| Flagship fixture | PASS; exactly 4 products in Four-product Demo, added without manual DB edits |
| Browser E2E | PASS; nine direct routes, four specialists, Balanced Growth, confirmation, execution and audit |
| Unsafe change | PASS; 50% Mouse increase rejected by existing 10% policy; failed action/invalid policy |
| Stale-state safety | PASS in backend regression; separate optional subset 3 tests covers changed price/cost and newly critical promotion inventory |
| Browser console/network | No unexpected errors/failing responses; outage injection is intentional and handled |
| Responsive | 1440 / 768 / 390 widths without page overflow |
| Screenshot capture | 15 actual browser PNGs; no AI-generated UI images or secret screens |
| Shopify | Mocked query/sync tests and browser import PASS; READ ONLY; no real store used |
| PostgreSQL deployment | Phase 13 verified empty PostgreSQL 17.11 migrations/seed, native production startup/APIs and private-demo execution/idempotent audit |
| Fresh Python installation | Phase 13 constrained temporary venv install, pip check clean and 560 tests PASS |
| Extracted submission ZIP | Integrity/per-file SHA-256 PASS; 560 backend tests PASS (17.57 s); offline npm ci, 76 frontend tests and build PASS |
| Docker / Nginx execution | NOT VERIFIED; binaries unavailable |
| Hosted/cloud/HTTPS/provider TLS | NOT VERIFIED; no destination/credentials configured |
| Remote GitHub Actions | NOT VERIFIED; workflow configured, equivalent local tests/build pass |
| Concurrent PostgreSQL locking stress | NOT VERIFIED; basic transaction/workflow execution is not a stress benchmark |

## Coverage and interpretation

Tests exercise pure decisions, schemas, ownership, boundaries, state transitions,
policy failures, stale sources, rollback, repeated execution, migrations, seed,
read-only Shopify mappings/pagination/failure handling, frontend states and API contract
selection. Confidence heuristics are not empirically calibrated accuracy measures.
No performance or revenue improvement percentage is inferred from passing tests.

The safe browser action changed Mouse local price 999.00→1048.95 after human approval
and separate confirmation. Audit showed execution_completed. The unsafe action failed
without modifying price. Shopify browser results use synthetic transport from the explicit
release demo helper, not a remote store. Agents themselves never execute actions.

## Evidence files

- [Final browser report](docs/examples/submission-browser.json)
- [Screenshot index](docs/screenshots/README.md)
- [Four-product structured plan](docs/examples/cross-agent-demo.json)
- [Production startup/API/CORS evidence](docs/examples/deployment-production.json)
- [PostgreSQL approval and idempotency](docs/examples/deployment-postgres-demo.json)
- [Dependency failure evidence](docs/examples/deployment-failures.json)
- [Phase 12 detailed matrix](phases/PHASE_12.md) and [Phase 13](phases/PHASE_13.md)

Earlier JSON performance values are isolated local ASGI samples, not hosted production
benchmarks. Earlier phase counts are historical; this document is the final regression
count. Final setup/demo details are in DEMO_SCRIPT.md and DEPLOYMENT.md.
