# CartPilot: manual Vercel Hobby + Neon Free deployment

Use this runbook for two projects from the same Git repository. The hosted service is
an **advisory-only synthetic-data demo**. Application authentication is absent.
`ENVIRONMENT=production` keeps action creation/review/execution and all Shopify routes
blocked. The full workflow stays local/private. Do not change environment to bypass gates.
The Integrations page explains this restriction and disables its Shopify controls when
the backend reports the production gate. A hosted Shopify 403 does not indicate a wrong
merchant or missing credentials. Adding a Shopify token does not enable these routes.

## 1. Select the code and free accounts

Merge the deployment-readiness PR into `main`, or explicitly select its branch for a
preview first. Git imports deploy pushed commits only. Verify the selected deployment's
commit in Vercel. Use a Vercel **Hobby** account and a Neon **Free** account. Do not accept
paid upgrades, add-ons, storage/auth/AI services or a card-required integration.

Inspect existing resources before creating any. Reuse `cartpilot-backend` in team
`king-09` if it is linked to `Priyanshuraj0909/CartPilot`. The observed project ID is
`prj_9hgLBdIBD7OroNPtHb0sPPrQbqQy`. Do not edit unrelated projects.

## 2. Create the disposable Neon database

1. Open https://console.neon.tech. Confirm the account's plan is **Free**.
2. Reuse a clearly identified CartPilot demo project, or create `cartpilot-demo` with
   **Postgres only**. Select a region near the backend (the existing backend uses `iad1`,
   so an available US East region is suitable). Keep Free compute/default autosuspend.
3. On the selected branch, create a dedicated database named `cartpilot_demo_20261003`
   and a dedicated database-owner role. Never reuse a valuable database for this demo.
4. In Neon SQL Editor select that exact database and check:

   ```sql
   SELECT tablename FROM pg_tables WHERE schemaname = 'public';
   ```

   The database must have no application tables before the initial migration. If it
   already contains data, create a new disposable database; do not delete/reset it.
5. In **Connect**, select that database and role, turn **Connection pooling off**, and
   copy the direct connection URL into a local ignored file/provider secret field.
   Never paste it into chat, Git, screenshots, browser build variables or terminal commands.
6. Use `postgresql+asyncpg://` (CartPilot also normalizes `postgresql://`). Preserve
   percent-encoded credentials. Retain the provider's `sslmode=require` (CartPilot maps
   it to asyncpg's `ssl=require`); this encrypts the connection. If the copied URL has
   `channel_binding=require`, remove that libpq-only query parameter for asyncpg;
   **retain TLS**. Do not provide both `ssl` and `sslmode`. For certificate and hostname
   verification use `ssl=verify-full` with `sslrootcert` pointing to a trusted CA bundle
   readable in each runtime. asyncpg does not automatically load system roots in this
   mode: do not select verify-full without configuring its CA bundle. `require` alone
   does not establish server identity.

Record the project ID, branch ID and database name without credentials for later inspection.

## 3. Create/reuse both Vercel projects before deploying

Open https://vercel.com/new and import `Priyanshuraj0909/CartPilot`. Keep both projects
in the same Hobby account. For an existing project, use **Settings → Build and Deployment**.

| Setting | Backend | Frontend |
| --- | --- | --- |
| Project name | Reuse `cartpilot-backend` | `cartpilot-frontend` |
| Production branch | `main` | `main` |
| Root Directory | **`backend`** | **`frontend`** |
| Framework | FastAPI | Vite |
| Install | Checked-in `pip install -r requirements-vercel.txt -c requirements.lock.txt` | `npm ci` |
| Build | No custom command | `npm run build` |
| Output | Framework default | `dist` |

Keep the checked-in `vercel.json` files. Backend's `.python-version` pins **3.12**;
`pyproject.toml` explicitly exports `app.main:app`. No Uvicorn command is needed.
**Root Directory is a project setting**, not a `vercel.json` field. A repository-root
backend import produces `FASTAPI_ENTRYPOINT_NOT_FOUND`; changing the entrypoint alone
cannot fix relative dependencies/imports when the project root is wrong.

Creation can trigger a build before settings are complete. A failed initial build is
not a completed deployment. Finish the environment/database setup before redeploying.
Copy each project's actual assigned production HTTPS origin from **Settings → Domains**.
Do not assume a name is available or append `/api/v1` to the API origin.

## 4. Configure environment variables and public demo access

In **Settings → Environment Variables**, add these for **Production**. Configure Preview
separately if used; its frontend origin must be explicitly authorized by backend CORS.
Do not expose valuable data on either environment.

| Project | Variable | Value |
| --- | --- | --- |
| Backend | `ENVIRONMENT` | `production` |
| Backend | `DATABASE_URL` | Secret asyncpg-compatible direct Neon URL from step 2 |
| Backend | `DATABASE_POOL_MODE` | literal string `null` |
| Backend | `REDIS_URL` | Empty value |
| Backend | `LOG_LEVEL` | `INFO` |
| Backend | `CORS_ORIGINS` | Actual frontend HTTPS origin, without trailing slash or path |
| Frontend | `VITE_API_URL` | Actual backend HTTPS origin, without trailing slash or `/api/v1` |
| Frontend | `VITE_CURRENCY` | `USD` (optional) |

If the environment editor disallows an empty Redis value, leave a checked-in `.env`
unuploaded and use a UI/API/CLI environment entry that supports an empty value. **Do
not omit REDIS_URL**: the application's default enables local Redis diagnostics.
Leave all Shopify credentials and merchant binding unset. No LLM key is needed.

For this public synthetic advisory demo, use **Settings → Deployment Protection** on
each project and choose a configuration that leaves the production domains public.
If the Hobby UI only offers a toggle, disable **Vercel Authentication** on these demo
projects. Existing settings protect backend default domains and can block API access.
Keep private previews protected where supported. Do not send a protection bypass token
from frontend code. This affects hosting access only; production application gates remain.

## 5. Run migrations, then explicitly seed once

Clone/update the selected merged commit locally. Create **backend/.env** in a private
editor with the six backend variables above. Git ignores this file and Vercel excludes
it; set the same settings independently in Vercel. Never copy the development example
URL/password into hosting. Ensure DATABASE_URL targets the dedicated empty demo DB.

macOS/Linux, starting from repository root:

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt -c requirements.lock.txt
python -m alembic upgrade head
python -m alembic current
# Run only after migrations succeed on the selected empty disposable database:
python -m app.core.seed
```

Windows PowerShell, starting from repository root:

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -c requirements.lock.txt
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
# Run only after migrations succeed on the selected empty disposable database:
.\.venv\Scripts\python.exe -m app.core.seed
```

Stop if migration fails. The migration head is `11shopify_read_only`; the expected seed
creates **1 merchant, 25 products, 110 orders**, inventory and price history. Do not
replace Alembic with schema guesses. Do not put migrations/seed in function startup,
Vercel builds or a public endpoint. For another reset use a new disposable database.

## 6. Deploy backend, then frontend

In backend **Deployments**, redeploy the selected `main` commit with the new settings.
Wait for **Ready**. Check public `/health`, `/api/v1/health/detailed` and `/docs`.
A detailed health HTTP 200 with `database=disconnected` is **not database readiness**.
Check build logs for root/entrypoint/dependency failures and runtime logs for safe error
classes. Do not print settings or connection strings while debugging.

Deploy/redeploy frontend after its actual API origin is configured. Wait for **Ready**.
If the frontend domain changed, update backend `CORS_ORIGINS` and redeploy the backend.
If the backend domain changed, update frontend `VITE_API_URL` and rebuild/redeploy it.

## 7. Verify hosting and browser behavior

From the repository root, using the same local virtual environment (replace the public
origin placeholders with the actual domains):

```bash
backend/.venv/bin/python scripts/deployment_smoke.py \
  --url https://ACTUAL-BACKEND-ORIGIN \
  --frontend-origin https://ACTUAL-FRONTEND-ORIGIN \
  --check-frontend
```

Windows uses `backend\.venv\Scripts\python.exe` with the same options on one line.
The checker verifies production/database/Redis health, Swagger UI, populated catalog,
four scoped analyses, successful Balanced Growth results, all action write/Shopify gates,
exact-origin CORS and POST preflight, nine direct SPA routes, API origin in the published
bundle, and missing-asset 404. Gate probes use invalid bodies to avoid valid action writes
if a gate regresses. Failures are explicit and omit raw response bodies/credentials.

Then open the frontend in a private browser window:

- Confirm Dashboard, Products and Inventory display seeded API data; Network requests
  must go to the configured backend origin and succeed without Vercel sign-in.
- Run Pricing, Restock, Promotion and Listing; inspect each visible result.
- In AI Manager select **Balanced Growth**, analyze the store and inspect the plan.
- Refresh each of the nine direct routes, including `/ai-manager` and `/products`.
- Check browser console/network for CORS, mixed-content, redirect or API errors.
- Approvals/execution and Shopify remain unavailable in production. Do not enable them.

The HTTP checker does **not** run a browser or prove interactive data rendering. Report
configured, deployed, HTTP-verified and browser-verified steps separately.

## Current connector limitations

The connected Vercel deployment call returned `Tool deploy_to_vercel not found`, and
project settings/environment mutation tools were not exposed. Neon project discovery
and creation were not exposed; inspection requires a project ID. Connections are not
local CLI credentials. These are provider-access blockers, not repository code defects.
No successful cloud deployment is claimed by this runbook.

## Official references

- https://vercel.com/docs/frameworks/backend/fastapi
- https://vercel.com/docs/functions/runtimes/python/python-version
- https://vercel.com/docs/deployment-protection/methods-to-protect-deployments/vercel-authentication
- https://vercel.com/docs/plans/hobby
- https://neon.com/docs/manage/projects
- https://neon.com/docs/guides/python
- https://magicstack.github.io/asyncpg/current/api/index.html
