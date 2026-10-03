# Deployment handoff — 3 October 2026

Status: local demo running; native production startup rechecked; cloud deployment pending a hosting target and account access. No public URL is claimed.

## Verified now

Fresh isolated SQLite database, all three migrations, explicit 25-product seed, native release/start scripts with the project virtual environment, production health, all four specialist APIs, orchestration, action reads, exact-origin CORS and production 403 write/Shopify gates passed. Evidence: `examples/final-production-start-check.json`. This check used SQLite, not managed PostgreSQL. Phase 13 records the earlier isolated PostgreSQL check separately.

When running scripts locally activate `backend/venv` first. An unactivated shell can select an unrelated Python installation; the first continuation attempt did so, then the same scripts passed with the project's virtual environment on PATH.

## Reviewable hosting configuration

| Component | Configuration |
| --- | --- |
| Backend root | `backend` |
| Build | `pip install -r requirements.txt -c requirements.lock.txt` |
| Release | `sh scripts/release.sh` |
| Start | `sh scripts/start.sh` |
| Health path | `/health`; inspect `/api/v1/health/detailed` for DB readiness |
| Python | 3.12 |
| Frontend root | `frontend` |
| Build | `npm ci && npm run build` with public `VITE_API_URL` set to the actual HTTPS API origin |
| Publish | `frontend/dist`; rewrite SPA routes to `/index.html` |
| Database | Dedicated managed PostgreSQL; provider-required verified TLS and backups |
| Access | Protected network/provider access control; application authentication is absent |

Backend environment: `ENVIRONMENT=production`, `HOST=0.0.0.0`, provider-supplied `PORT`, actual `DATABASE_URL`, exact frontend `CORS_ORIGINS`, `LOG_LEVEL=INFO`, and blank `REDIS_URL` when optional Redis is unused. Shopify secrets remain omitted unless a separate protected integration setup is requested. No credentials belong in source or VITE settings.

Production mode intentionally blocks action writes and Shopify routes. For a complete faculty workflow use the loopback demo, or a provider-access-controlled private development environment after that boundary is established. Do not bypass these gates to expose the application publicly.

## Pending target-specific work

Select provider/account and private access method; create the dedicated database; configure environment secrets; run the release; publish backend/static frontend; verify HTTPS, SPA routes, exact CORS, health and safety gates against actual URLs. Provider commands, pricing, region and TLS settings must be checked against its current official documentation once selected. No provider resources were created or charged during this continuation.
