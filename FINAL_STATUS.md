# CartPilot current verified status

Updated 21 October 2026 (Asia/Kolkata). This supersedes Phase 14's authentication and
activity limitations. Historical phase evidence remains in its original documents.

The merchant MVP is implemented and locally verified. Four deterministic specialists
and a Master Orchestrator provide explainable advisory plans; merchant approval and
separate fresh-state validation protect local/simulated execution. No LLM, trained
forecasting model or autonomous learning is implemented.

| Capability | Current boundary |
| --- | --- |
| Accounts and store management | Signup/login/logout, hashed revocable sessions, account-scoped catalog CRUD/archive, sales import and in-app stock alerts |
| Account attempt protection | Atomic database-backed budgets across instances for signup/login/forgotten-email recovery; 429 and Retry-After |
| Forgotten login email | Store name and password prove ownership; replacement email updates atomically and revokes sessions; no email verification or forgotten-password delivery |
| Specialists and orchestration | Deterministic guarded pricing/restock/promotion/listing rules, priorities, conflicts, synergies and partial results |
| Saved Agent Activity | Merchant-scoped orchestration summaries survive sessions; standalone specialist cards remain session-only |
| Approval and audit | Explicit review, separate confirmation, fresh-state checks, duplicate protection, rollback and persistent action audit |
| Price/listing execution | Local database only; not synchronized to Shopify |
| Restock/promotion execution | Simulation only; no stock arrival, supplier orders or campaign launch |
| Shopify | Read-only sync; static token or cached client credentials; optional scheduled worker code and mocked lifecycle tests |
| Production permissions | Business APIs require account identity; action writes and Shopify API routes remain blocked |
| Infrastructure | Migration 16_reliability, frontend API proxy, deployment configuration and GitHub CI including disposable PostgreSQL checks |

## Verification

- Backend: 635 passed; two PostgreSQL checks skipped by default and passed separately.
- Frontend: 146 passed; TypeScript/Vite production build passed.
- Fresh SQLite migration upgrade/downgrade retains legacy runs and recommendations.
- Fresh PostgreSQL migration passed; concurrent auth budget and duplicate execution passed.
- GitHub CI, three Vercel deployments and same-origin hosted probes passed (details below).

See [test evidence](TEST_SUMMARY.md), [release guide](docs/RELIABILITY_RELEASE.md) and
[Phase 16](phases/PHASE_16.md) for scope and reproduction.

## Remaining work

Email verification/password reset delivery, persistent worker hosting, live Shopify
validation, provider ingress controls, backup restoration, broader load/security/browser
UAT, measured outcome feedback and validated demand forecasts remain incomplete.
No measured revenue uplift or full public-production readiness is claimed.

## Deployment preparation

The configured CartPilot Neon database was migrated from 15_accounts to 16_reliability
on 21 October 2026. Merchant, account, product, order and session row counts were
unchanged. No seeding, catalog edits or commerce execution occurred. GitHub confirms
automatic Vercel checks for cart-pilot, backend-cartpilot and cartpilot-backend.
Release [90a47de](https://github.com/Priyanshuraj0909/CartPilot/commit/90a47dee9dbd9d4ece412c5d2c011f47baaf73dc)
was pushed to main. [GitHub Actions](https://github.com/Priyanshuraj0909/CartPilot/actions/runs/39615089349)
passed backend, frontend and PostgreSQL jobs. All three Vercel commit statuses report
success: cart-pilot, backend-cartpilot and cartpilot-backend.

The live frontend contains saved activity, email recovery and rate-limit messaging.
Its same-origin detailed health returns 200 with production/database connected/Redis
disabled; auth status requires accounts; the new activity endpoint returns 401 without
a session and Cache-Control: no-store; /agent-activity serves the SPA. A reserved
nonexistent login returns 401 without account creation.

Direct probes of backend-cartpilot.vercel.app from this environment failed with
URLError; the frontend API proxy works. An authenticated hosted merchant walkthrough
and the additional backend's runtime remain unverified. These HTTP checks do not prove
full production readiness. See [structured evidence](docs/examples/reliability-release.json).
