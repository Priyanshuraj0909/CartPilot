# Phase 16 — Merchant reliability and release

Authorized by the user on 21 October 2026 following a repository review, including
publishing verified work to GitHub and updating the existing deployments.

Implemented:

- Accessible signup/recovery store-name help linked to the input.
- Atomic database-backed signup/login/recovery attempt limits across instances.
- Merchant-scoped saved AI Manager plan summaries with bounded pagination, UTC times,
  partial-result visibility and activity refresh/loading/error/empty states.
- Duplicate-email recovery rollback preserves the original identity and sessions.
- Shopify client-credential caching, expiry validation and one-time 401 renewal;
  ordinary transient retries retain their independent configured budget.
- Tests for the existing read-only scheduled worker and email-recovery continuation.
- PostgreSQL migration and targeted concurrency CI using a disposable database.
- Current status, test evidence and deployment documentation reconciled with source.

Migration: 16_reliability follows 15_accounts. It adds auth_rate_limits and nullable
agent_runs.merchant_id. Old unowned activity stays hidden; product/order/account data
is retained. Never run test cleanup against store databases.

Verification: 635 backend tests pass; two opt-in PostgreSQL tests pass separately;
146 frontend tests and TypeScript/Vite build pass. Fresh SQLite upgrade/downgrade and
PostgreSQL migrations pass. Full release evidence is in FINAL_STATUS.md and
TEST_SUMMARY.md; publish/deployment evidence is recorded after the release completes.

Remaining milestones: email verification/password reset through an email provider,
live-store Shopify validation, persistent worker hosting, provider ingress controls,
backup restoration/load/browser UAT, validated forecasting/outcome feedback and any
external execution integration. None are represented as completed by this phase.
Production action/Shopify API restrictions and human approval remain in place.
