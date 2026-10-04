# CartPilot

**The AI Manager Sitting on Top of Your Inventory**

*A Multi-Agent E-Commerce Decision and Operations Management System*

CartPilot is an e-commerce decision-support MVP. Four deterministic specialists analyze
pricing, replenishment, promotions and factual listing quality. The Master Orchestrator
coordinates goal-based recommendations, conflicts, synergies and dependencies. Eligible
proposals pass through policies, human approval, separate confirmed local/simulated
execution and persistent audit. No LLM, forecasting ML or autonomous learning is implemented.

**READY WITH MINOR LIMITATIONS for a trusted faculty demo, viva and source submission.**
Account authentication and merchant scope are implemented in the Phase 15 continuation.
General public production readiness still requires further security and infrastructure review.
Shopify is READ ONLY; local price/listing changes are never pushed to it. Restock and
promotion execution are simulations, not real supplier orders/campaigns.

## Problem, solution and objectives

Pricing, stock, discounts and catalog maintenance can produce conflicting decisions
when reviewed separately. CartPilot centralizes their shared signals, provides explainable
specialist proposals, prioritizes review by merchant goals and blocks unsafe actions.
The objective is demonstrable coordination and safety, not an unmeasured revenue lift.
Implemented/read-only/simulated boundaries are listed in [FINAL_STATUS.md](FINAL_STATUS.md).

## Submission and demo guide

- [DEMO_SCRIPT.md](DEMO_SCRIPT.md): seven-minute four-product demo and exact offline fallback.
- [VIVA_QA.md](VIVA_QA.md): quick-reference sheet and 52 source-matched questions/answers.
- [PROJECT_REPORT_OUTLINE.md](PROJECT_REPORT_OUTLINE.md): abstract, report structure and 12-slide content outline.
- [Current testing review](docs/testing/CURRENT_TEST_REVIEW.md): **583 backend / 89 frontend** tests, build results and current verification limits.
- [Testing procedure](docs/testing/STEP_BY_STEP_TESTING.md) and [manual test sheet](docs/testing/MANUAL_TEST_CASES.csv): reproducible acceptance checks; manual results remain pending.
- [TEST_SUMMARY.md](TEST_SUMMARY.md): historical Phase 14 **560 backend / 76 frontend** results.
- [Screenshots](docs/screenshots/README.md): 15 real browser captures; Shopify panel is explicitly mocked.
- [Algorithms](docs/ALGORITHMS.md) and [API/data/security reference](docs/API_DATABASE_SECURITY.md).
- [SUBMISSION_CHECKLIST.md](SUBMISSION_CHECKLIST.md): source archive generation and institutional items.

## Project structure

```text
backend/
  app/agents/                  specialist interfaces
  app/services/                signals, rules, orchestration, policies and workflow
  app/models/ + app/schemas/    persistence and typed API contracts
  app/api/v1/                  implemented HTTP routes
  alembic/                     versioned migrations
  tests/                       isolated regression and offline fixtures
  scripts/                     separate release/start commands
frontend/
  src/components/ + pages/     nine-route UI, recommendation/action components
  src/services/                typed backend client and formatting
  tests/                       Vitest/React Testing Library
phases/                        historical implementation/verification records
scripts/                       verification, capture and submission utilities
docs/                          formulas, references, JSON evidence and screenshots
.github/workflows/             tests/build CI configuration
```

## Architecture and stack

Shopify / Demo Data → existing Data Layer → four Agents → Master Orchestrator →
Cross-Agent Intelligence → Unified Action Plan → Policy Validation → Human Approval →
separately confirmed, revalidated Local/Simulated Execution → Audit Log.

- Backend: Python 3.12+, FastAPI, Pydantic, async SQLAlchemy, Alembic, httpx.
- Frontend: React 18, TypeScript, Vite, Tailwind CSS and Lucide icons.
- Persistence: PostgreSQL 16 target; isolated SQLite test/demo databases.
- Redis 7: optional diagnostics; disconnected Redis yields degraded health without
  preventing recommendation or execution APIs.

Read [ARCHITECTURE.md](ARCHITECTURE.md) for actual boundaries and safety behavior.
Verified locally with Python **3.12.7** and Node **26.10.0**. Existing Dockerfiles target
Python 3.12 and Node 24; container runtime could not be tested because Docker is absent
in this environment. Use a supported Node release compatible with the checked-in
Vite dependency tree; the exact tested version is reported rather than a patch pin.

## Local setup

From repository root:

```bash
cp .env.example .env
# Edit local environment values as needed; never commit this file.
docker compose up -d postgres redis
```

Settings load repository-root `.env`, then optional `backend/.env`; process environment
variables have highest precedence. Frontend credentials must never contain Shopify
access tokens. Set VITE_API_URL to the backend URL and VITE_CURRENCY to your display
currency (USD by default). Display currency does not convert stored prices.

In a backend terminal:

```bash
cd backend
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt -c requirements.lock.txt
alembic upgrade head
python -m app.core.seed
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Apply migrations before seeding. The seed is development data: 1 merchant, 25 products,
25 inventory records, 110 orders and 25 price-history records. It skips reseeding when
merchants already exist. Never seed a valuable production database.

In a frontend terminal, from repository root:

```bash
cd frontend
npm ci
npm run dev -- --host 127.0.0.1
```

Open `http://localhost:5173/dashboard`; backend OpenAPI is at
`http://localhost:8000/docs`. API versioned routes begin `/api/v1`.

If Docker is unavailable, an isolated local SQLite demo can be used with an absolute
path to a new disposable file. Before backend migration/seed/server commands, export:

```bash
export ENVIRONMENT=development
export DATABASE_URL=sqlite+aiosqlite:////absolute/path/to/disposable-demo.sqlite
```

The standard seed supports varied demand/stock; the deterministic four-product fixture
below demonstrates the exact slow-mover, poor-listing and healthy-product scenario.
Root `.env` may contain other settings; process values override it. Phase 13 verified
fresh PostgreSQL migrations and basic execution; provider TLS and concurrency stress
remain deployment checks.

## Environment variables

`.env.example` contains placeholders and documented local-development defaults.
DATABASE_URL, REDIS_URL and CORS_ORIGINS configure infrastructure. Pricing/restock/
promotion/listing limits and MAX_ACTIONS_PER_PLAN configure existing guardrails.
Production CORS requires explicit origins; CORS is not authentication.
LOG_LEVEL defaults to INFO; production rejects DEBUG and requires explicit DATABASE_URL.
Set REDIS_URL= to disable optional Redis diagnostics. Frontend Vite reads root .env,
but exposes only public VITE_ settings. A production build without VITE_API_URL uses
same-origin /api/v1 and requires an API reverse proxy. Separate hosts require an explicit URL.

Shopify uses SHOPIFY_STORE_DOMAIN, SHOPIFY_ACCESS_TOKEN, SHOPIFY_MERCHANT_ID and a
centralized SHOPIFY_API_VERSION (currently configured as 2026-10). Required read scopes:
`read_products`, `read_inventory`, `read_orders`. The token belongs only in backend
settings. Configure an existing, preferably dedicated merchant and select it in the UI.
Integration routes are development/test only.

Read [Phase 11 setup](phases/PHASE_11.md) for current token acquisition, scopes, variant
identity, location aggregation, order status/refund mapping, missing cost, pagination,
rate limits and limitations. No real-store connection was exercised in final tests.

## Testing and reproducibility

```bash
cd backend
venv/bin/python -m pytest -q
# Clean migrations, safe downgrade/upgrade, seed and full HTTP demo:
venv/bin/python -m pytest tests/test_release_bootstrap.py -q
# Isolated performance and seed report (no network/developer DB):
venv/bin/python -m tests.release_checks
# Existing offline scenario demos:
venv/bin/python -m tests.demo_cross_agent
venv/bin/python -m tests.demo_shopify
cd ../frontend
npm run test:run
npm run build
```

The frontend build runs TypeScript checking. Lint is not configured. Tests use fresh
SQLite fixtures, enabled foreign keys, mocked health/services and synthetic Shopify
HTTP. They do not rely on a real store, internet, developer credentials or persistent
DB state. The existing root `scripts/verify_foundation.sh` runs the full regression
and frontend build despite its historical filename.

Phase 12 source also passed from an isolated copy containing all non-ignored tracked
and untracked submission files; frontend dependencies were installed with offline
`npm ci`. That Phase 12 check was not a committed fresh clone or a clean Python dependency installation:
Python tests reused the installed virtual environment. That historical reproduction does not certify the current committed source.
Use the current testing review for the latest regression results.

## Demo flow

1. Load seeded/local data or use Integrations → Test Connection → Sync Now.
2. Review Dashboard, Products and Inventory; open a product and run each specialist.
3. In AI Manager choose Balanced Growth and Analyze Store (maximum 100 products).
4. Review priorities, blocked work, conflicts, synergies and original proposals.
5. Create an eligible action for review; inspect its policy and proposed change.
6. In Approvals approve/reject. Approval does not execute or change product data.
7. Execute an approved action through separate confirmation and fresh policy checks.
8. Show resulting local/simulated outcome, Price History and Action History.
9. Repeat execution to demonstrate idempotency; stale/unsafe proposals remain blocked.

The real Chrome walkthrough covered all nine pages, all four analyses, Balanced Growth,
local price execution/audit and mocked Shopify sync. Browser widths 1440/768/390 had
no page overflow or unexpected console/network failures. Backend-disconnection errors
remain useful, and local data works independently of Shopify availability.

Evidence: [browser results](docs/examples/release-browser.json),
[performance/seed results](docs/examples/release-performance.json),
[four-product plan](docs/examples/cross-agent-demo.json), and
[Shopify offline results](docs/examples/shopify-demo.json).

### Offline four-product browser demo

For the exact verified scenario without touching your developer DB, run from backend:

```bash
release_demo_db=$(mktemp /tmp/cartpilot-demo.XXXXXX)
export ENVIRONMENT=test DATABASE_URL="sqlite+aiosqlite:///$release_demo_db"
export CORS_ORIGINS=http://127.0.0.1:5174
export SHOPIFY_STORE_DOMAIN= SHOPIFY_ACCESS_TOKEN=
venv/bin/python -m alembic upgrade head
venv/bin/python -m tests.release_demo
```

In another terminal, from frontend:

```bash
VITE_API_URL=http://127.0.0.1:8012 npm run dev -- --host 127.0.0.1 --port 5174
```

Open `http://127.0.0.1:5174`. Select **Four-product Demo** for the coordinated scenario,
then **Shopify Offline Demo** for synthetic read-only synchronization. These Shopify
HTTP responses are mocked; the Connected badge in this fixture does not mean a real
store was accessed. Stop both servers with Ctrl+C after the demonstration.

## Current limitations

Phase 15 adds account authentication and server-bound merchant scope, including legacy
single-product analysis. Production requires authentication; anonymous seeded demos
remain available in development/test by default. See
[account and store management](docs/ACCOUNT_STORE_MANAGEMENT.md) for setup and limits.
General public launch still requires ingress rate limits and broader security/load audits.

Live Shopify permissions/token behavior and PostgreSQL concurrency are unverified here;
Docker is unavailable. Shopify sync is manual, capped and synchronous, covers recent
orders, may lack cost data and can retain a busy flag after process death. Deleted
records/older-order changes need reconciliation. No automatic credential refresh,
webhooks, Shopify writes, currency conversion or real supplier operations exist.

Catalog sales aggregates remain per product despite eliminating redundant product
loads. Performance evidence is a small SQLite/ASGI sanity check, not production load
capacity. Backend requirements use lower bounds rather than a release lock; no CVE
scan or fresh online dependency resolution is claimed. Dependency versions were not
broadly upgraded. Two unused frontend helper packages were removed after import review.

Earlier phase documents preserve historical implementation snapshots. Phase 12
and this README describe the final MVP. No new business feature or integration was
added during hardening.

## Deployment (Phase 13)

See [DEPLOYMENT.md](DEPLOYMENT.md) for provider-neutral static hosting, the Python
service, PostgreSQL migrations, explicit demo seed, optional Redis, HTTPS/CORS,
SPA routing, backend-only Shopify configuration and troubleshooting. Start the
backend with `sh scripts/start.sh` from backend; apply migrations separately with
`sh scripts/release.sh`. Neither startup command seeds or resets data.

Production remains advisory: guarded writes and Shopify routes stay blocked. The
full approval/Shopify faculty demo must use an isolated, access-controlled private
development/test environment. Phase 15 subsequently adds authentication. The Phase 13 evidence does not certify
the current hosted application; see the current testing review for hosted check limits.
[Phase 13 evidence](phases/PHASE_13.md) distinguishes actual PostgreSQL/start/build/browser
checks from Docker, remote CI, provider hosting and live Shopify checks not performed.

## Agent overview and final boundaries

Pricing proposes bounded changes with cost/movement protection; Restock proposes lead-time
replenishment; Promotion checks excess inventory, trends and retained margin; Listing
uses grounded text/attribute checks. Master Orchestrator selects and coordinates these
by six merchant goals. [AGENTS.md](AGENTS.md) preserves development rules and describes
all five roles. Exact formulas and examples are in [ALGORITHMS.md](docs/ALGORITHMS.md).

## Future scope and final stop

Measured forecasting, supplier adapters, approved Shopify writes, additional platforms,
password recovery/email verification and outcome learning remain future work.
Account authentication and merchant authorization were added in Phase 15. No new feature
is included in the final package. Phase 14 completes documentation/demo/submission
preparation; see [PHASE_14.md](phases/PHASE_14.md). Stop development unless a real defect
or explicit project-guide request requires it.

### Requested final report and PowerPoint

The [editable report, PDF and 12-slide PPT](docs/deliverables/README.md) were generated
on explicit request after Phase 14. Academic identity fields remain marked placeholders.
The [deployment handoff](docs/DEPLOYMENT_HANDOFF.md) records the latest native startup
verification and the information needed for actual hosting.

### Vercel + Neon deployment preparation

[Setup and account steps](docs/VERCEL_NEON.md) cover two Vercel projects and a Neon database.
Local preparation passed 564 backend tests, 76 frontend tests and the production build.
Actual cloud deployment remains pending account connections; production writes remain gated.

### Account and store management continuation

[Setup and current limits](docs/ACCOUNT_STORE_MANAGEMENT.md): signup/login/logout,
production account authorization, product create/edit/archive, sales CSV import,
recorded-sales ranking and stock alerts. Apply `python -m alembic upgrade head` before
using accounts. For authenticated local use set REQUIRE_AUTH=true in the backend and
VITE_REQUIRE_AUTH=true in the frontend, then restart/rebuild. Production always requires
accounts. Historical academic artifacts describe the earlier MVP snapshot.
