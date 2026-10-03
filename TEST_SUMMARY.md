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
