# Phase 12 — Final Testing, Security Hardening & Release Readiness

**Status: COMPLETE. Release: READY WITH MINOR LIMITATIONS for a trusted local faculty
demo and project submission. Public multi-tenant production deployment: NOT READY.**
Verification date: 3 October 2026 (Asia/Kolkata). No major product feature, agent,
commerce platform, integration, LLM capability or autonomous execution was added.

## Verification matrix

| Category / feature | Test type | Expected behavior | Actual result / evidence | Status |
| --- | --- | --- | --- | --- |
| Foundation health/root/CORS | API + failure injection | Liveness, truthful DB/Redis diagnostics, explicit origins | health suite + four component-state combinations; missing Redis degraded, app usable | PASS |
| Data layer constraints/isolation | SQLite integration with FK enabled | Reject orphan/negative/duplicate rows, retain scope, cascade order lines | data-layer suite + Phase 12 orphan/cascade checks | PASS |
| Alembic clean bootstrap | Disposable file DB + subprocess | upgrade, downgrade -1, upgrade; insert/seed valid rows | full bootstrap test; percent-containing URL covered | PASS |
| Seed volume/idempotency | Migrated DB + API | merchant, 20+ products, 100+ orders, stock/history, no repeat duplication | 1 merchant, 25 products, 110 orders, 25 inventories, 25 histories; reseed skipped | PASS |
| Pricing rules/persistence | Unit + database + HTTP | Margin/change limits, demand, safe insufficient data, determinism, no mutation | pricing suites; pending caller changes never flushed; scoped frontend/API | PASS |
| Restock rules/persistence | Unit + database + HTTP | Available/reserved/unavailable stock, demand/lead-time/safety, capped quantity | restock suites + shared analytics/no-autoflush tests | PASS |
| Promotion guardrails | Unit + API | Safe margin/cap, demand trends, stockout/unknown-cost suppression | promotion suites; stale approved discount blocked at execution | PASS |
| Listing grounding | Unit + API | Preserve factual source/negations, request unsupported details, no invention | listing suites + grounded-output rejection + browser analysis | PASS |
| Master Orchestrator | Unit + API | Controlled routing, ownership, bounded store scope, determinism, partial results | orchestration suites; 100-product cap, truncation, inactive scope, agent failure | PASS |
| Cross-agent priorities | Four-product fixture + API/browser | Inventory safety first; conflicts, synergies, dependencies, stable ordering | Mouse restock first; speaker promotion; poor listing; healthy product; existing safety override tests | PASS |
| Policy validation/approval/rejection | HTTP + database | Every action validated and separately human-reviewed | all four action policies + approval/rejection/isolation tests | PASS |
| State machine | Exhaustive unit transitions | Only documented transitions valid | 81 source/target combinations; allowed transitions pass, all others reject | PASS |
| Safe execution/revalidation | Failure injection + HTTP/browser | No unapproved/stale execution, rollback, idempotency | fresh checks, duplicate execution, CAS/SQLite concurrency, executor/audit rollback tests | PASS |
| Audit log | Database + API/browser | Major events recorded; scoped, no credential logging | creation/review/start/completion/block/failure events; browser history verified | PASS |
| Shopify reads/mappings | HTTP MockTransport + database | All variants/locations/order lines, stable identities, no PII/customer import | 72 Phase 11 tests remain passing; mock browser imports 3 variants/3 inventories/1 order | PASS |
| Shopify failures/limits | Synthetic HTTP | Sanitized auth/network/malformed/partial errors; bounded retries/cursors | 401/403/429/5xx/timeouts, Retry-After, throttle restoration, page/cursor limits | PASS |
| Shopify write safety | Static audit + tests | Queries only; agents cannot call Shopify; actions local/simulated | fixed registry contains no mutation; invalid arbitrary query rejected | PASS |
| API failure contract | HTTP + injected exceptions | 403 scope, 404 missing, 409 workflow, 422 validation, safe 503/500 | centralized sanitized storage/unexpected responses, generic error boundary | PASS |
| Logging/secrets | Repository/build-context scan + tests | No real credentials/raw errors/SQL bind values | no credential-pattern findings; .env variants ignored; Docker contexts exclude secrets | PASS |
| Timestamp/money integrity | Typed contracts + unit/database | UTC serialization, Decimal monetary guardrails | SQLite timestamps normalized; two-decimal bounds + discounted-unit rounding tested | PASS |
| Frontend navigation/states | Vitest + real Chrome/CDP | All nine pages, analysis, loading/empty/errors, scoped calls | 71 tests; initial network failures fixed on integration/approval/history pages | PASS |
| Browser responsiveness/console | Real headless Chrome, isolated API | No overflow/unhandled warnings; useful backend-down failure | 1440/768/390 widths; zero unexpected console/network errors | PASS |
| Performance sanity | 25-product seeded SQLite/ASGI, 3 samples | Bounded work and practical local responsiveness | products ~31 ms, inventory ~38 ms, pricing ~3 ms, Balanced Growth ~58 ms median | PASS, MVP only |
| Clean submission source copy | Isolated non-ignored source files | Tests/build independent of working-tree paths | Python 542 tests using existing venv; offline npm ci + 71 tests/build | PASS with setup limits |
| Docker runtime | Environment availability | Compose config/up and containers usable | Docker executable unavailable | NOT VERIFIED |
| Live PostgreSQL locking/migrations | Deployment DB | PostgreSQL-specific behavior validated | No live deployment DB verification attempted | NOT VERIFIED |
| Real Shopify connection/token | Development store | Actual installed app/scopes/token work | No real store credentials supplied; automated tests intentionally mocked | NOT VERIFIED |
| Production identity/public ingress | Security design review | Authentication and authorization on caller identity | MVP scope checks only; development routes gated; public deployment prohibited | LIMITATION |
| CVE/fresh online dependency install | Dependency review | Resolved packages audited from authoritative feeds | No CVE scan/online Python dependency resolution claimed | NOT VERIFIED |

## Exact results and runtime

- Backend: **542 passed** (434 previous tests + **108 Phase 12 tests**).
- Frontend: **71 passed** (66 previous tests + **5 Phase 12 tests**), without React
  act warnings after correcting the new async test waits.
- Frontend production build: passed, including TypeScript checking.
- Lint: not configured; no artificial lint-disable workarounds.
- Migrations: clean upgrade → downgrade -1 → upgrade and seed/API flow passed on
  isolated SQLite; legacy preservation/lossy-downgrade guards remain passing.
- Seed: 1 merchant, 25 products, 25 inventory, 110 orders and 25 price-history rows.
- Python: 3.12.7; Node: 26.10.0. Dockerfiles specify Python 3.12/Node 20 but could not
  be run in this environment. Versions were not broadly upgraded.
- `git diff --check`: passed. No user database was migrated, reseeded or destroyed.

## Bugs reproduced and corrected

1. Pricing/Restock API requests did not validate selected merchant ownership, unlike
   Promotion/Listing. Added optional strict merchant_id scope, preflight checks and
   frontend scope submission; four-agent foreign-scope tests return 403. Legacy
   unscoped calls remain supported; authenticated identity is explicitly not claimed.
2. Shared pricing/restock reads could autoflush pending caller edits with an autoflush
   session. The shared read function now suppresses autoflush; rollback proves no
   accidental persistence. No agent writes were added.
3. The detailed-health regression contacted developer DB/Redis. Tests now set safe
   process config before importing the app, mock health, and enable fixture foreign
   keys. Failure combinations are deterministic and independent of infrastructure.
4. Development SQL echo/raw probe exceptions could expose stored bind data or sensitive
   diagnostics. SQL echo is disabled, bind parameters hidden, probes bounded, and
   only exception types are logged. Unexpected API exceptions are intercepted before
   server middleware can re-raise raw messages into logs; response details are generic.
5. Pricing/Restock/catalog unhandled storage errors lacked the sanitized 503 contract
   used by newer endpoints. Added global SQLAlchemy handling and safe 500 boundary.
6. README's root `.env` setup was not honored from backend cwd. Settings now resolve
   root/backend `.env` paths deterministically, preserving environment override priority.
7. Initial migrations used raw `now()` defaults: SQLite upgrade appeared successful
   but seed inserts failed. Portable `sa.func.now()` compiles to the dialect's timestamp
   default. PostgreSQL semantics stay unchanged; clean migrated SQLite now seeds.
   Existing already-migrated SQLite files with the old bad defaults are not silently
   rebuilt—use a new disposable demo DB or a reviewed repair, preserving valuable data.
8. Percent signs in DB URLs were not escaped for Alembic ConfigParser. Initial config
   assignment escapes them; the actual async engine still receives the original URL.
   A percent-containing SQLite path covers this clean-bootstrap regression.
9. Catalog reloaded Product/Inventory for every already-eager-loaded product. Signals
   can reuse the validated page product; the regression verifies one product-page
   read. Remaining per-product sales aggregates are documented, not hidden.
10. Integrations/Approvals/Action History did not show the shared initial merchant-load
    failure when the backend was unavailable. They now surface a useful error.
11. SQLite public product/inventory/price-history dates could serialize without a
    timezone. UTC normalization fixes these responses consistently with existing
    action timestamps. SQLite app connections also enable foreign keys.
12. Production wildcard CORS could be configured despite credentialed middleware.
    Production settings now reject wildcard origins; explicit local defaults remain.
13. Git ignored `.env` but not every `.env.*` variant, and Docker contexts lacked secret/
    dependency/database exclusions. Added protections without deleting any existing data.
14. Dependency import audit found unused `clsx` and `tailwind-merge`; removed only these
    frontend packages and their lock entries. No dependency-version upgrade was made.
15. Architecture/README still described LangGraph, LLM learning, a foundation-only phase
    and outdated advisory-only UI. Final docs now reflect implemented deterministic
    specialists, guarded local execution and read-only integration honestly.

## Security findings

Critical: no unresolved critical defect detected within the tested trusted local/demo
boundary; no real credential-pattern findings in tracked/non-ignored repository content.
No token values or ignored `.env` contents were printed or included in evidence.
This scan does not prove unseen credentials/historical commits are clean, and does not
claim a penetration test or vulnerability-feed audit.

Important: no authenticated merchant identity, no public multi-tenant authorization,
legacy optional scope, no public ingress hardening. CORS and request merchant IDs are
not substitutes for authentication. Production action/Shopify routes remain blocked.
SQLite concurrency tests do not establish live PostgreSQL guarantees. Backend lower
bounds are not a release dependency lock. These block public deployment, not a trusted
local faculty demonstration.

Minor/demo limits: optional Redis may remain degraded, display currency must match
source money, Shopify cache freshness and process-crash busy recovery are manual.
Demo credentials are synthetic; no real external store is modified.

## Performance and dependency review

[Measured report](../docs/examples/release-performance.json) records three ASGI samples
against 25 products/110 orders: listing uses 80 queries, single Pricing 5 and Balanced
Growth 177. Median/max times are reported directly in the artifact; these are local
SQLite observations, not PostgreSQL/network latency or production capacity.

Catalog relationship loading is eager and now reused. Three analytical aggregates
still run per product; orchestration additionally gathers trend/listing context. This
is a remaining linear query cost, acceptable in the measured small demo but worth
batching before larger deployment. Product/store/sync limits bound work; no unbounded
analysis/retry/pagination loop was found. No claim of a full load test is made.

The existing minimal backend dependencies cover implemented functions. Frontend now
uses React, Lucide and its build/test stack; two unused class helpers were removed.
No new dependency, LLM library, parallel persistence layer or major upgrade was added.
Docker context exclusions reduce accidental secret/venv/node_modules copying.

## End-to-end and browser evidence

The isolated migrated-DB HTTP test exercises seed/reseed, catalog/health, all four
agents, four-product Balanced Growth, unapproved execution denial, action creation,
approval, confirmed local price execution, duplicate execution, audit and unsafe-policy
blocking. Existing action tests separately cover rejection, stale approval, all four
policies, failure savepoints, completion-audit failure and concurrent idempotency.

The [real Chrome report](../docs/examples/release-browser.json) covers all nine pages,
four agents, Balanced Growth, the approval/confirmation dialog, successful local price
change and visible audit history, then a mocked Shopify sync. The test switches only
isolated demo merchants; the source fixture contains the four-product scenario and
original 25-product seed. No manual database edits or real-store credentials are needed.
Desktop/tablet/mobile widths have no document overflow. Mobile screenshot was visually
inspected. Browser-disconnected API produces an explicit error instead of an empty
card. Expected injected network failure is excluded from the zero-unexpected-error count.
This was a headless automated real-browser walkthrough, not a claim of human clicking.

`tests/release_demo.py` refuses non-test/non-SQLite configuration; run only with a new
migrated disposable file. `scripts/release_browser.mjs` connects to the dedicated local
Chrome debug port and demo frontend ports. No browser automation dependency was added;
this optional script uses the native WebSocket available in the tested Node version.
Temporary browser/API/frontend processes were stopped after verification.

## Reproduce

```bash
# From backend, after installing documented dependencies:
venv/bin/python -m pytest -q
venv/bin/python -m pytest tests/test_release_hardening.py tests/test_release_bootstrap.py -q
venv/bin/python -m tests.release_checks
venv/bin/python -m tests.demo_cross_agent
venv/bin/python -m tests.demo_shopify
# From frontend:
npm ci
npm run test:run
npm run build
# On the intended development DB, not a valuable production DB:
# alembic upgrade head
# python -m app.core.seed
```

The source-copy check used every non-ignored tracked/untracked submission file under
`/private/tmp`, installed frontend packages offline from cache, and ran tests/build.
It reused the installed Python venv; no clean online Python install is claimed. A literal
Git clone currently would contain only committed earlier phases: all later source must
be included in the submission or reviewed/committed before creating a release clone.

## Documentation, Git and release recommendation

README: finalized setup/environment priority, actual seed/migration commands, test/demo
flow, versions and limitations. Architecture: rewritten to match actual implemented
boundaries. PLAN and MASTER_ORCHESTRATOR point to final Phase 12. Historical phase docs
retain their earlier snapshots; Phase 12 is the final current-state reference.

Branch: `main`. Existing HEAD: `ec45c41` (Phase 2). No new commit was created; user-owned
prior-phase changes remain alongside intentional Phase 12 fixes/test/docs. No ignored
credentials, dependency directories, build outputs or DB dumps were staged/committed.

Recommended: faculty demo and project submission using the complete tested source.
For the next deployment phase, first implement/review authenticated identity and public
access boundaries, validate PostgreSQL migrations/locking, verify Docker/live Shopify,
lock/audit dependencies, and plan sync recovery/freshness. Those are remaining work,
not implemented features. Stop after Phase 12; no Shopify writes or new business scope.
