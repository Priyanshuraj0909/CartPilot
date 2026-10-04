# Phase 15 — Account and merchant workflow continuation

Explicitly requested by the user after the final MVP audit. This supersedes the Phase
14 feature-development stop for account and store-management work.

Implemented locally: signup/login/logout; scrypt passwords and revocable hashed opaque
sessions; production business authentication and merchant scope; account-scoped catalog
create/edit/archive; price history; bounded idempotent sales import; recorded sales
ranking/revenue; on-demand stock notifications; frontend account gate and management UI.

Production gates for action writes and Shopify routes remain. Not implemented: email
verification/recovery, delivered email, full admin console, provider rate controls,
supplier/campaign/Shopify external execution. No cloud migration or deployment occurred.
A new Alembic revision adds account/session tables. Read docs/ACCOUNT_STORE_MANAGEMENT.md.

Do not claim public production readiness or erase prior phase evidence. Tests use
isolated SQLite; browser accessibility and concurrency/provider audits remain pending.

Local verification: 569 backend tests, 78 frontend tests, TypeScript/Vite build,
fresh SQLite migrations and whitespace check passed. This is an implemented local
continuation, not a cloud release. Provider migration, visual browser verification,
load testing and email/provider work remain outstanding.


## Local connection and performance repair — 2026-10-04

User-requested repair: the frontend was running without a backend. The backend's
provider environment additionally selected production authentication/CORS and NullPool.
`scripts/dev.sh` and `Start CartPilot.command` now start the local services with explicit
development mode, local CORS and pooled connections, using the configured database.
They perform no migrations/seeding; existing services are reused, production env files
are preserved, and account management retains its authentication requirement.

Catalog aggregates recent/lifetime orders and price-history counts in two batch queries
per page, with merchant/status/time bounds retained. Same-merchant refresh retains visible
data while loading; switching merchants clears it. Regression coverage verifies bounded
query count, no-sales/empty pages, invalid lookback, merchant isolation and refresh failures.

Verification: 587 backend tests, 92 frontend tests and TypeScript/Vite build passed.
Agent-browser verified dashboard and Products (25 rows), API Connected, backend reachable,
no browser errors or Vite overlay. Read-only comparison of the previous catalog/signals
code against the new implementation on the configured database measured 8.325 s versus
0.801 s for 25 products with identical product metrics/revenue. This single local sample
includes connection warmup and is not a load-test or a universal latency guarantee.
Launcher syntax and already-running-service reuse passed. No cloud deployment occurred.

## Hosted login recovery repair — 2026-10-05

A one-shot auth-status failure previously persisted as “Backend unavailable. Reload to
retry,” while any `/auth/me` failure deleted the saved token. Hosted login now uses
its already-required authentication setting without a redundant status request.
Session verification retries transient network/502/503/504 failures at most three
attempts, preserves tokens during outages, and offers Retry connection. Only a 401
expires the session. Unmounted checks are cancelled. Login/signup writes are never
automatically retried; request deadlines cover response-body reading so the form
unlocks after timeout and merchants can retry deliberately.

Verification: 587 backend tests, 134 frontend tests and TypeScript/Vite production build passed,
including transient recovery, retry exhaustion/manual recovery, expired sessions,
failed-login retry and slow response-body timeout. Read-only hosted probes confirmed
backend status/health, configured CORS and an expected 401 for nonexistent credentials.
The historical screenshot does not establish the original provider outage cause;
these repairs prevent the confirmed client recovery defects from persisting.
