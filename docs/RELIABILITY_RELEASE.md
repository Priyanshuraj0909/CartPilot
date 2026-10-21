# Reliability release — 21 October 2026

This release strengthens the merchant MVP and includes the previously uncommitted
password-proven email recovery and optional read-only Shopify worker continuation.
It adds no dependencies, external write permissions or paid infrastructure.

## Shared account attempt limits

Signup, login and forgotten-email recovery use atomic database upserts before password
hashing. All instances share counters in auth_rate_limits. Per route, defaults allow
10 attempts for a normalized email/store identity and 100 attempts for an ASGI peer
within 900 seconds. Both successful and rejected requests consume budgets. Counters
expire without extending the window when a request is blocked. Long-expired counters
are cleaned during subsequent authentication requests. Keys are SHA-256 digests;
passwords, tokens, raw email/store names and IP addresses are not stored in counters.
Hashing is pseudonymization, not a guarantee against dictionary recovery.

Configure AUTH_RATE_LIMIT_WINDOW_SECONDS, AUTH_RATE_LIMIT_IDENTITY_ATTEMPTS and
AUTH_RATE_LIMIT_PEER_ATTEMPTS in the backend. A blocked request returns HTTP 429 with
Retry-After. A counter storage outage fails closed with a sanitized 503. No Redis is
required. Forwarded headers are not trusted by application code; set trusted proxy
handling at the ASGI server/provider and add provider ingress controls. Peers behind
a shared proxy/NAT share the peer budget. Limits are supplementary controls, not a
complete abuse-protection service.

## Saved AI Manager activity

POST /api/v1/orchestrate saves a compact AgentRun summary after analysis. The summary
contains the goal, product/recommendation counts, completion flag and failed-analysis
count. It does not persist raw customer data or implicitly approve or execute actions.
Pure specialist/orchestrator services remain advisory and do not persist these runs.

GET /api/v1/agent-runs?merchant_id=ID supports offset and limit (default 50, maximum
100). Authenticated access is bound to the account merchant. Legacy records without
merchant ownership are excluded. Agent Activity retrieves summaries across sessions;
standalone specialist activity cards still describe the current browser session.
The feed shows partial plans. Invalid scopes and failed requests do not create runs;
infrastructure failures before a summary can be committed remain API errors.

## Release order

1. Run backend pytest, frontend Vitest and the production build.
2. Run migration/targeted concurrency checks against an isolated PostgreSQL database.
3. Check the configured deployment database revision without exposing credentials.
4. Apply python -m alembic upgrade head to each intended backend database before serving
   new code. Do not seed or reset existing accounts/catalog/orders.
5. Push the verified commits to main; inspect GitHub CI and each configured Vercel
   deployment status. Compare the live OpenAPI agent-runs route and frontend saved
   activity content with the release source.
6. Check backend health, same-origin API proxy, authentication and direct SPA routes.
   Keep live verification read-only unless an isolated test account is explicitly used.

The additive migration is 16_reliability. Existing products, orders and sessions are
retained. If rolling application code back, keep the additive schema; downgrading the
migration discards new activity ownership and limiter counters. Test downgrade is only
verified on disposable data. Provider backup and restore verification remains necessary
before managing valuable store data.

## PostgreSQL checks

CI creates an isolated PostgreSQL 17 database named cartpilot_ci, migrates it, and runs
backend/tests/test_postgres_integration.py. The tests accept only that exact database
name and deliberately clear application rows in that disposable test database.
Never point CARTPILOT_TEST_POSTGRES_URL at a store database. To reproduce:

```bash
cd backend
# DATABASE_URL must point at the disposable migrated cartpilot_ci database.
python -m alembic upgrade head
CARTPILOT_TEST_POSTGRES_URL="$DATABASE_URL" python -m pytest tests/test_postgres_integration.py -q
```

The two tests cover concurrent shared auth budgets and two concurrent attempts to
execute the same approved local price action. This is targeted concurrency coverage,
not a production stress benchmark. The standard suite skips them unless configured.

## Shopify and remaining milestones

Shopify remains read-only. Client credentials are for an app and store in the same
organization; see Shopify's official [client credentials guide](https://shopify.dev/docs/apps/build/authentication-authorization/client-credentials-grant).
Tokens are cached until near expiry, and a rejected token is renewed once. Transient
GraphQL retries do not repeatedly acquire tokens or gain an extra retry when no 401
occurs. Mocked tests cover these paths; they do not prove real-store configuration.

The optional worker needs a persistent host and backend-only credentials. Vercel
Functions do not provide that lifecycle. It is disabled by default; this release does
not enable or provision it. Production Shopify HTTP routes remain gated.

Email verification, forgotten-password recovery, delivered notifications, live-store
validation, broader security/load/browser UAT, backup restoration, measured outcome
feedback and validated forecasting are separate remaining milestones. Supplier orders,
live promotions and Shopify writes require adapters and separately reviewed execution.
