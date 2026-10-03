# Phase 13 — Deployment & Production-Style Environment Setup

Status: **COMPLETE for deployment configuration and isolated production-style verification.**
No cloud provider/account/public URL was supplied; this is not a claim of a live hosted
release. No business feature, new agent, integration, authentication, external write,
autonomous execution or Phase 14 work was added.

## Architecture and access

Static React/TypeScript frontend → HTTPS FastAPI service → managed PostgreSQL.
Redis is optional diagnostics. Shopify remains backend-only and read-only.
See [DEPLOYMENT.md](../DEPLOYMENT.md) for the diagram, generic service settings,
HTTPS/CORS, database backups/limits, safe reset, Shopify and troubleshooting.

Production mode remains advisory: existing local action writes and Shopify routes are
403. The complete human approval flow uses a **protected private development demo**
with the same production entry point/static frontend. Test-mode offline Shopify is
mocked. These modes do not bypass action approval, execution confirmation or policies.
Without authentication, neither read-only nor demo mode should be public multi-tenant
hosting. Provider/private-network access restriction is required.

## Changes

- Central validated development/test/production modes and local-route policy property.
- Production requires DATABASE_URL; supported PostgreSQL URL schemes normalize to
  asyncpg, preserving escaped credentials and mapping sslmode to ssl. Invalid config
  hides input values. Port bounds and configurable log levels; production DEBUG refused.
- Non-reloading `scripts/start.sh` uses HOST/PORT/log settings. Separate migration-only
  `scripts/release.sh`; neither migrates/seeds automatically during serving startup.
- Explicit FastAPI debug false; safe version/environment startup message. Connection
  refusals now receive sanitized 503 like SQLAlchemy storage errors. Other unexpected
  errors remain sanitized 500; sensitive payloads are not logged.
- Empty REDIS_URL disables probing and reports disabled; configured Redis failures
  still degrade diagnostics without breaking business APIs. Async Redis close updated.
- Existing frontend VITE_API_URL preserved. Production has no implicit localhost
  fallback; omitted URL uses same-origin API and requires a reverse proxy. Separate
  hosting explicitly supplies the backend HTTPS URL. Vite reads root .env but exposes
  only VITE_ keys. Docker uses build arguments, not ineffective runtime API variables.
- Frontend recovery boundary displays reload controls after unexpected render errors.
- Backend non-root Python image selectively copies app/release files; Node 24 builder
  and explicit Nginx SPA fallback/caching. Docker ignores cover secrets/caches/dumps.
  Compose retains local infrastructure, passes backend Shopify settings and frontend
  build args, and no longer makes Redis a backend startup dependency.
- Verified backend dependency constraints; minimal GitHub Actions tests/build workflow
  without production secrets. Root env example uses actual settings; future unused
  API-key/JWT examples removed. Git ignore covers coverage/database dumps.
- README, architecture, master current-phase pointer and plan updated. Deployment
  documentation and reproducible read-only HTTP smoke/browser evidence added.

## Verification

| Check | Result / exact scope |
| --- | --- |
| Previous backend regression plus 18 deployment tests | **560 passed** |
| Fresh Python environment, constrained installation | PASS; pip check clean; full **560 passed** again |
| Frontend regression plus 5 deployment checks | **76 passed** |
| TypeScript + Vite production build | PASS; frontend/dist generated and ignored |
| Configured HTTPS API bundle | PASS; https://api.example.test present, implicit localhost URL absent, Shopify token setting absent |
| Development / HTTPS production / same-origin API selection | PASS; frontend tests |
| Lint | NOT CONFIGURED; no fabricated lint pass |
| Empty PostgreSQL migration | PASS; isolated PostgreSQL **17.11**, all three revisions to 11shopify_read_only |
| Explicit PostgreSQL demo seed | PASS; 1 merchant, 25 products/inventory/history and 110 orders before separate four-product fixture |
| Production start | PASS; sh scripts/start.sh, ENVIRONMENT=production, custom PORT=8013, no reload |
| Production HTTP APIs | PASS; DB connected, Redis disabled, catalog/inventory, four agents, balanced growth, action reads |
| Production CORS | PASS; exact configured origin allowed; unknown origin not trusted |
| Production safety gates | PASS; action creation and Shopify status blocked 403 |
| Invalid deployment configuration | PASS; unsupported mode/driver/URL, missing production URL, port limits and production DEBUG validated without input leakage |
| Unreachable PostgreSQL + Redis | PASS; liveness ok, detailed health degraded/disconnected, store API safe 503 |
| Configured unavailable Redis / optional disabled Redis | PASS; existing regression plus new disabled-Redis test and actual failure smoke |
| Built-frontend real Chrome smoke | PASS; nine pages loaded directly, four agents, balanced growth, approval/confirmation/execution/audit, mocked Shopify sync |
| Responsive / API outage browser | PASS; 1440/768/390 widths without overflow, useful connection failure, no unexpected console/network failures |
| PostgreSQL full private-demo HTTP flow | PASS; four products/agents, orchestration, unapproved execution 409, approval, safe execution, repeat idempotency and execution_completed audit |
| Shopify read-only + timeout boundaries | PASS in existing mocked regression/browser; no live store |
| Git/secret/bundle review | PASS; secret/generated artifacts ignored, no frontend backend-secret exposure, no new commit made |
| Docker / Nginx container execution | NOT VERIFIED; Docker and Nginx executables unavailable; configs reviewed |
| GitHub Actions hosted run | NOT VERIFIED; workflow added; equivalent local checks passed |
| Provider deployment / HTTPS ingress / managed TLS | NOT VERIFIED; no hosting destination configured |
| PostgreSQL 16 container / concurrency stress | NOT VERIFIED; migration/API/execution checks used isolated PostgreSQL 17.11, not locking stress |

## Evidence and reproduction

- [Production APIs/CORS/gates](../docs/examples/deployment-production.json)
- [Dependency failure](../docs/examples/deployment-failures.json)
- [Built frontend and direct routes](../docs/examples/deployment-browser.json)
- [PostgreSQL approval/execution/audit](../docs/examples/deployment-postgres-demo.json)
- `scripts/deployment_smoke.py`: real HTTP read-only checks for an isolated seeded
  production service; specify --url and configured CORS origin per DEPLOYMENT.md.
- `scripts/release_browser.mjs`: existing browser helper now checks direct navigation
  and accepts DEMO_FRONTEND_URL / DEMO_BROWSER_REPORT, preserving Phase 12 evidence.

All temporary servers/databases belong to this verification task. No developer DB
or real store was used. Seed, migrations and four-product demo initialization were
explicit. Production-style tests used disposable data; production write gates were
never relaxed to make the demo pass.

## Remaining release limitations

No production authentication/identity binding or public API rate limiting. Existing
legacy omitted-merchant analysis scope remains compatible. No Shopify writes, supplier
orders, real replenishment/promotion execution or autonomous actions. CORS is not
access control. Docker/platform/live Shopify verification is still needed on the
chosen host. The source working tree also contains earlier phases' uncommitted work;
include all intended source/config/test/docs files in submission, never .env/builds.

Phase 14 readiness: configuration, reproduced tests, isolated PostgreSQL run, browser
workflow and deployment evidence are ready to support faculty demonstration, final
write-up, PPT and submission. **Phase 14 is not implemented. Stop after Phase 13.**
