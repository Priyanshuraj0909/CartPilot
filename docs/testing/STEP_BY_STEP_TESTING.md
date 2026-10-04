# CartPilot testing: nine-step review

Reviewed 4 October 2026 against current source. Historical phase results are retained;
local regression does not certify the deployed application.

## Step 1: Find critical features

| Feature | Current implementation | Test evidence |
| --- | --- | --- |
| Login/register/logout | Implemented; hashed passwords, expiring revocable sessions | backend/tests/test_accounts_management.py; frontend/tests/Accounts.test.tsx |
| Product management | Authenticated create/edit/archive, inventory and price history | test_accounts_management.py; StoreManagement.test.tsx |
| AI agent execution | Four deterministic specialists and goal orchestrator; guarded local actions | test_*_agent.py, test_cross_agent.py, test_orchestrator.py, test_actions.py |
| Revenue analysis | Recorded sales totals and product ranking; no measured revenue uplift | test_accounts_management.py; StoreManagement.test.tsx |
| Recommendations | Typed pricing/restock/promotion/listing output and explicit history persistence | specialist API, rule and persistence tests; Recommendations.test.tsx |
| Database operations | ORM, migrations, isolated persistence, rollback and import deduplication | test_data_layer.py, migration/bootstrap/action tests |
| API endpoints | FastAPI health, auth, catalog, management, specialists and workflows | backend/tests/test_*_api.py and account/health tests |

Limitations: password recovery/email verification, cart recovery and real supplier or
campaign execution are absent. Promotion/restock execution is simulated. Development
allows anonymous seeded demos by default; production requires account authentication.

## Step 2: Test manually first

Open MANUAL_TEST_CASES.csv in Excel and save your executed copy as .xlsx. Fill Actual
Result and Status only after performing each test; attach screenshots or a bug reference.
Use a disposable local store and a unique test email. Enable backend REQUIRE_AUTH=true
and frontend VITE_REQUIRE_AUTH=true for the account journey; restart both services.
Follow README.md for service setup. Run register → login → create product → import sales
→ inspect revenue → analyze → refresh → logout. Record date, version, browser and environment.
Automated test passes must not be copied into the manual-result columns.

## Step 3: Run backend tests

pytest, pytest-asyncio and httpx already exist in backend/requirements.txt. No extra
test dependency is needed. From the repository root:

```sh
cd backend
venv/bin/python -m pytest -q
```

The suite uses httpx ASGITransport with async fixtures rather than a new synchronous
TestClient. conftest.py selects disposable SQLite and disables real Shopify credentials.
Do not point regression tests at your store database.

## Step 4: Test APIs

Use the running backend /docs to inspect current schemas. Business routes use /api/v1.
Check status, response fields/types, error detail and absence of unintended data changes.

| API | Positive result | Negative checks |
| --- | --- | --- |
| GET /health and GET / | 200 health/metadata | Storage diagnostics are separate from liveness |
| POST /api/v1/auth/signup | 201 session and identity | Invalid email/password 422; duplicate email 409 |
| POST /api/v1/auth/login | 200 session | Wrong password 401 |
| GET /api/v1/auth/me | 200 own identity | Expired/revoked/missing session 401 |
| POST /api/v1/products | 201 ID | Invalid fields 422; duplicate SKU 409 |
| PUT /api/v1/products/{id} | 200 ID | Foreign/missing product 404; invalid stock 409 |
| DELETE /api/v1/products/{id} | 200 archived status | Confirm historical sales remain |
| POST /api/v1/sales/import | Imported/skipped counts | Empty 422; conflicting repeat 409 |
| GET /api/v1/analytics | Own revenue and ranked products | Missing session 401 |
| GET /api/v1/notifications | Own stock alerts | Missing session 401 |
| GET /api/v1/products?merchant_id=ID | Scoped catalog | Foreign authenticated scope 403 |
| POST /api/v1/{pricing,restock,promotion,listing}/recommend | Structured recommendation | Invalid 422; foreign 403; missing product 404 |
| POST /api/v1/orchestrate | Scoped advisory plan | Invalid input/scope; partial specialist failure |
| Action and Shopify routes | Local guarded workflow/read-only sync | Production writes/integration routes remain 403 |

This table is a starting matrix, not proof of exhaustive route coverage. Inventory,
history, action review/execute and integration routes also require testing; see
../API_DATABASE_SECURITY.md and registered routers in backend/app/main.py.

## Step 5: Evaluate agents

FUNCTIONAL_CHECKLIST.md contains 30 fixed acceptance conditions. Run them with pinned
fixtures and record input, expected predicate, actual output, status and test reference.
Existing regression covers many conditions; a separately labeled 30-case benchmark
has not been produced by this review. Do not assume a 20% sales decline always warrants
a discount: cost, margin, stock and history guardrails determine the answer. Cart
abandonment is unsupported because no cart events/recovery agent exist.
Report passed/executed supported cases as rule conformance, not prediction accuracy.

## Step 6: Verify failures

Existing tests cover invalid email/empty input, API error displays, sanitized storage
503 errors, unexpected 500 errors, action rollback and partial specialist failures.
Run test_release_hardening.py, test_accounts_management.py, orchestration tests and
frontend/tests/ApiErrors.test.ts. Inject storage failure only in isolated fixtures.
There is no external LLM call to fail; specialist exceptions are the relevant failure.
Never return a success status for a failed operation merely to satisfy a test.

## Step 7: Check monitoring

Partial: startup/shutdown, storage failures, pricing analysis, specialist failures,
Shopify sync and persistent action audit events exist. Dedicated login success/failure
and uniform agent-start/recommendation-generated events are not implemented throughout.
Hosted log collection, alerts and deployment monitoring are not verified here.
To complete this step, add consistent sanitized event logging and verify capture;
never log passwords, bearer tokens, credentials or raw customer payloads.

## Step 8: Write the testing report

Use CURRENT_TEST_REVIEW.md for this run and TEST_SUMMARY.md for historical Phase 14
results. Include unit, API/integration, functional, frontend and user acceptance testing.
For module counts, record actual collected/executed tests and outcomes; do not copy the
example 10/15/20 counts. Manual UAT remains pending until the Excel sheet is filled.
Keep browser, production, performance and provider results separate from local tests.

## Step 9: Retest deployment safely

First use the deployed version and record URL, version, environment and reproducible
bugs. Fix one issue locally, rerun its tests plus relevant regression/build, deploy the
reviewed change and retest the same journey. This review makes documentation changes
only; it does not migrate, reset, or redeploy a database/application. A fresh hosted
walkthrough and deployment monitoring remain pending.
