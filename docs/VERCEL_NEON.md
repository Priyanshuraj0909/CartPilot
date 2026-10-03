# CartPilot deployment: Vercel + Neon

Prepared 3 October 2026. Configuration is prepared locally; account connections and actual cloud deployment are pending. No cloud resource or live URL is claimed.

## Neon

Create a Free project with a dedicated empty PostgreSQL database. Choose a region close to the Vercel backend. Save credentials only in provider environment settings or a local ignored file, never frontend settings or chat.

Use an asyncpg-compatible connection string with provider-required TLS. CartPilot normalizes postgresql:// and sslmode to asyncpg/ssl. If the copied URL includes the libpq-only channel_binding parameter, obtain an asyncpg-compatible string; do not disable TLS. Use verified TLS where supported.

Initially use the direct endpoint with DATABASE_POOL_MODE=null. A pooled endpoint can be selected after checking compatibility. NullPool closes idle connections per request but does not cap concurrent requests. Use the direct endpoint for migrations.

In a local backend terminal, activate the existing virtual environment, securely load DATABASE_URL, set ENVIRONMENT=production, then run:

```bash
source venv/bin/activate
sh scripts/release.sh
# Only for the dedicated disposable synthetic-demo database:
python -m app.core.seed
```

Migrations/seed are explicit, never run on function startup or every build. Ordinary seed has 25 products, not the four-product offline mocked server fixture. Do not seed real merchant data.

## Backend Vercel project

Import this Git repository with root directory `backend`, framework FastAPI. Configuration uses the existing `app/main.py` app, Python 3.12 and constrained runtime dependencies. No Uvicorn start command is needed.

| Environment variable | Value |
| --- | --- |
| ENVIRONMENT | production |
| DATABASE_URL | Secret Neon PostgreSQL URL with TLS |
| DATABASE_POOL_MODE | null |
| REDIS_URL | Empty |
| LOG_LEVEL | INFO |
| CORS_ORIGINS | Exact assigned frontend HTTPS origin |

Omit Shopify credentials. Configure preview environments explicitly too. Function duration is set to 60 seconds, subject to actual account/runtime support. Test heavy analysis on the deployed service. Separate-project deployment protection may block browser API requests; verify access explicitly rather than passing a secret in browser code.

## Frontend Vercel project

Import the same repository with root `frontend`, framework Vite, install `npm ci`, build `npm run build`, output `dist`. Set public VITE_API_URL to the backend HTTPS origin without /api/v1. Deploy frontend, then update backend CORS_ORIGINS to its assigned origin and redeploy backend. API URL changes require frontend rebuilds.

The checked-in SPA rewrites exclude asset/file paths. Test all nine direct pages and confirm missing assets return 404 rather than HTML.

## Verify actual hosting

Check /health, /api/v1/health/detailed, /docs and /api/v1/merchants. Liveness alone does not establish database readiness. Run:

```bash
backend/venv/bin/python scripts/deployment_smoke.py \
  --url https://YOUR-BACKEND.vercel.app \
  --frontend-origin https://YOUR-FRONTEND.vercel.app
```

Verify browser catalog, all specialists, orchestration, CORS, error states and cold-start behavior. Production action writes and all Shopify routes must return 403. This is an advisory synthetic-data deployment; authentication is absent, and the full approval/execution demo stays local unless protected access is established.

The working tree has uncommitted phases. Git import deploys only pushed content; local Vercel CLI can upload the current working tree after login. Nothing was pushed during preparation. Connect the Vercel and Neon integrations to continue account-specific deployment.

## References and limits

[Vercel FastAPI](https://vercel.com/docs/frameworks/backend/fastapi), [Python runtime](https://vercel.com/docs/functions/runtimes/python), [function limits](https://vercel.com/docs/functions/limitations), [Hobby plan](https://vercel.com/docs/plans/hobby) and [Neon Free](https://neon.com/faster).

Hobby is for personal non-commercial use within quotas. Cloud builds, actual Neon TLS/driver compatibility and provider runtime remain unverified until connected deployment. Local tests establish application behavior, not provider compatibility.

## Local preparation verification

3 October 2026: 564 backend tests passed (18.27 seconds), 76 frontend tests passed,
TypeScript/Vite production build passed, production app import with actual NullPool
selection passed, and git diff whitespace validation passed. Four deployment tests
were added for valid/invalid pool settings and repeated serverless-style connections.
Historical Phase 14 documents/report correctly retain the earlier 560-test snapshot.
