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
