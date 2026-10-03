# PHASE 06 — FRONTEND DASHBOARD & RECOMMENDATION EXPERIENCE

Status: COMPLETE. Phase 7 has not been implemented.

## Delivered

- Dashboard: live catalogue, low-stock and stockout counts, recent orders/revenue,
  saved recommendation count, inventory health, and backend diagnostics.
- Products: searchable catalogue, pagination, stock/status and product detail drawer.
- Inventory: real coverage, sales velocity, risk, and inventory status filters.
- AI Manager: supported goal selection, up to 100 selected products, actual orchestrator
  response, priority ordering, conflict resolution, compatibility, and partial errors.
- Recommendations: Pricing/Restock/Action Plan cards and agent/risk/status/product
  filters; separate saved records and explicitly labelled current-session analyses.
- Agent Activity: actual session results for Pricing, Restock, and Orchestrator;
  Promotion and Listing are labelled Coming Soon.

Shared components include Shell, ProductTable, ProductDrawer, recommendation cards,
semantic badges, retry alerts, loading/empty states, and centralized formatters.
The drawer supports keyboard focus trapping, Escape, focus restoration and scroll locking.
All pages have responsive layouts, visible focus styles, and reduced-motion support.

## Data and API contracts

`frontend/src/services/api.ts` centralizes typed requests and friendly HTTP errors.
Abortable requests and merchant scope changes prevent stale analyses being displayed.

| Integration | Endpoint | Status |
| --- | --- | --- |
| Health | GET /api/v1/health/detailed | Working |
| Merchants | GET /api/v1/merchants | Working |
| Products | GET /api/v1/products?merchant_id=1 | Working |
| Inventory | GET /api/v1/inventory?merchant_id=1 | Working |
| Pricing | POST /api/v1/pricing/recommend | Working |
| Restock | POST /api/v1/restock/recommend | Working |
| Orchestrator | POST /api/v1/orchestrate | Working |
| Saved recommendations | GET /api/v1/recommendations?merchant_id=1 | Working |

New store endpoints are read-only. They reuse existing sales/restock analytics and
schema payloads. Merchant lists omit emails; product and recommendation reads are
merchant-scoped, including rejecting malformed saved references to foreign products.
Missing or invalid inventory remains visible without fabricating signals.
The UI shares a catalogue snapshot for Products and Inventory rather than requesting
identical data twice. Money accepts backend decimal strings and numbers.

Recent order/revenue metrics use the configured restock lookback (14 days by default),
exclude cancelled orders, and exclude future orders. Sales velocity reuses existing
unit analytics. Stockout risk and inventory states reuse Restock signals.
Product total is merchant-wide; inventory aggregates cover loaded products, with
pagination controls to load more. Requests return at most 100 products; standalone
inventory returns the first 100. Saved recommendations are capped at the latest 200.

## Run and demo

Use the README setup to run PostgreSQL/Redis, apply migrations, and seed development
store data. Run backend port 8000 and frontend port 5173; set `VITE_API_URL` if needed.
`VITE_CURRENCY=USD` defaults the presentation to dollars. This is a display convention,
not conversion: the current database model has no currency field.

1. Open Dashboard and inspect real metrics and backend health.
2. Search Products, open a product, inspect inventory and price history.
3. Run Pricing Analysis and Restock Analysis; read reasons, confidence, and risk.
4. Open Inventory and filter coverage/status.
5. In AI Manager select a supported combined goal and one or more products; run
   analysis and inspect the returned prioritized plan and original agent results.
6. Review Recommendations and filter results, then inspect Agent Activity.

The browser demo used the existing seed in an isolated in-memory SQLite backend:
25 products, 41 recent orders, $4,869.80 recent revenue, four low-stock products,
and zero saved recommendations. Keyboard SKU-EL-003 returned a price hold at
$119.50 and a 33-unit restock proposal. The combined keyboard/merino analysis
returned 33- and 32-unit restock proposals, overall high risk, confidence 60%, and
required approval. These are observed demo outputs, not hardcoded frontend data.

## Verification

- Backend: `venv/bin/python -m pytest -q` — 185 passed, including 11 store API tests.
- Frontend: `npm test -- --run` — 24 passed.
- TypeScript/Vite: `npm run build` — passed.
- Lint: no lint script is configured.
- Installed Chrome verified navigation and real API loading on all six pages,
  both individual analyses, multi-product orchestration, saved-empty states,
  session activity, and offline error/retry behavior.
- Responsive checks: all six pages at 1024, 768, and 390 pixels without page overflow;
  desktop and mobile screenshots visually inspected. Tables scroll within containers.
- No unexpected browser console errors or failed HTTP requests during online demo.

Browser verification used a separate seeded SQLite instance, not production data.
API ownership, invalid/missing inventory, pagination, no-write behavior and saved
records are additionally covered by backend tests. Frontend tests cover loading,
errors, search, filters, merchant switching, navigation, and analysis responses.

## Safety and limitations

No price changes are executed. No inventory changes are executed. No purchase orders
are placed. No merchant actions are automatically executed. Analysis endpoints do
not save proposals; existing optional persistence services remain separate.
Approval indicators explain that review is required; there are no Approve/Reject or
execution controls. Orders/Approvals/Action History pages are deferred under the
Phase 6 brief rather than displaying fabricated activity.

Session history is memory-only, capped at 100 results, and clears on reload or merchant
switch. It is not persisted AgentRun history. Empty saved recommendations are expected
until records have been saved elsewhere. No authentication was added; merchant scope
validation is not a replacement for authenticated authorization in production.
Promotion and Listing agents, approval execution, and external store integrations
remain future work. Reusable cards, typed contracts and the API layer support Phase 7.
