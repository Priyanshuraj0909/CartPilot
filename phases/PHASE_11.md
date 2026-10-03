# Phase 11 — Shopify Read-Only Integration

Status: **COMPLETE — implementation and mocked verification**. Live connection/sync
requires the developer's store credentials and has not been verified against a real
store. Phase 12 has not been implemented.

**Phase 11 Shopify integration is READ ONLY. No Shopify merchant data is modified.**
The backend issues fixed Admin GraphQL queries over HTTPS POST. There are no mutation
queries, arbitrary-query routes, Shopify write adapters, webhooks, unattended jobs,
OAuth onboarding, customer import or Shopify calls inside agents. Phase 9 execution
still uses the existing local/simulated workflow and approval checks. Sync can replace
local price/listing edits on mapped products with Shopify values; it never sends them
back to Shopify.

## Architecture and configuration

`integrations/shopify/queries.py` is the closed read registry; `client.py` handles HTTP,
timeouts, pagination and retries; typed source/result schemas validate responses;
`mapper.py` defines pure projections; `sync.py` persists into existing Product,
Inventory, Order and OrderItem models. Three small metadata tables track connection,
variant/product/inventory IDs and order IDs. Location IDs and quantities are retained
in the mapping's inventory snapshot. Tokens and customer data are absent from metadata.

The API version is centralized in Settings as `SHOPIFY_API_VERSION=2026-10`, checked
against [Shopify's current GraphQL reference](https://shopify.dev/docs/api/admin-graphql/2026-10/queries/products)
on implementation date 3 October 2026. A mismatched `X-Shopify-API-Version` response
is rejected rather than silently accepting a version fallback.

Required **read-only scopes**: `read_products`, `read_inventory`, `read_orders`.
[Location](https://shopify.dev/docs/api/admin-graphql/latest/objects/Location) accepts
`read_inventory`, so `read_locations` is unnecessary for these nested reads.
[InventoryItem](https://shopify.dev/docs/api/admin-graphql/latest/objects/InventoryItem)
unit cost also depends on the user's product-cost permission/data. No write scopes
are requested. [Order access](https://shopify.dev/docs/api/usage/access-scopes) normally
covers the last 60 days; we query a rolling 59-day window and do not request
`read_all_orders` or customer scopes.

Backend variables (see `.env.example`):

| Variable | Meaning |
| --- | --- |
| SHOPIFY_STORE_DOMAIN | Bare `store-name.myshopify.com` hostname; no URL/path/port |
| SHOPIFY_ACCESS_TOKEN | Admin API credential, backend only, masked SecretStr |
| SHOPIFY_API_VERSION | Supported quarterly version; default 2026-10 |
| SHOPIFY_MERCHANT_ID | Existing positive CartPilot merchant ID, explicitly bound |
| SHOPIFY_TIMEOUT_SECONDS | Per-request timeout, default 30, maximum 60 |
| SHOPIFY_MAX_RETRIES | Retries after initial request, default 3, maximum 5 |
| SHOPIFY_MAX_PAGES | Maximum pages per connection, default 100; incomplete on cap |
| SHOPIFY_READ_COSTS | Default true; false skips optional unitCost reads |

No new package is needed: the existing httpx, Pydantic, SQLAlchemy and Alembic stack
is reused. Missing credentials do not affect the demo catalog or startup. Merchant
binding prevents a selected merchant importing another configured store. Domain
changes cannot reuse a bound cache, and one store cannot bind two local merchants.
Integration routes are development/test only, matching the MVP's unauthenticated
local approval workflow. Merchant binding is not production authentication.

## Developer setup

1. Create a Shopify development store and an app in the Shopify Dev Dashboard.
2. Configure only the three read scopes above and install the app on the intended
   store. Follow [Shopify's authentication documentation](https://shopify.dev/docs/apps/build/authentication-authorization).
   For an app and store owned by the same organization, the current
   [client credentials flow](https://shopify.dev/docs/apps/build/authentication-authorization/client-credentials-grant)
   can obtain an Admin API token. This MVP consumes the token manually; it does not
   store a client secret or implement token acquisition/refresh. If Shopify issues
   a short-lived token (for example 24 hours), obtain a fresh one when it expires.
   Legacy installed custom-app tokens can also be supplied where available.
3. Use an existing, preferably dedicated CartPilot merchant (`GET /api/v1/merchants`);
   do not delete or replace seeded demo merchants. This phase adds no merchant
   provisioning or authentication workflow.
4. Set the backend environment's domain, token and merchant ID. Use `.env` locally
   or your secret manager; never put a token in frontend/VITE variables or Git.
   Omit SHOPIFY_MERCHANT_ID until ready to configure it; do not set it to an empty string.
5. Run `cd backend && venv/bin/python -m alembic upgrade head` on your intended
   database, then start backend/frontend using the README's existing commands.
6. Select the bound merchant, open `/integrations`, and test the connection.
7. Click **Sync Now**. Read the summary and any partial failures before analysis.

## Mapping and synchronization

| Shopify data | CartPilot representation |
| --- | --- |
| Parent product | Shared title, plain-text description, type/category, source date, status |
| Each variant | Separate Product with its own price/SKU and external variant identity |
| Missing/duplicate SKU | Stable `SHOPIFY-{variant numeric ID}` fallback; hash fallback on local collisions |
| Inventory item | Product mapping holds its external inventory item ID |
| Active location levels | Aggregate on_hand; committed + reserved becomes reserved_quantity |
| Other unavailable stock | unavailable_quantity = on_hand − available − committed − reserved |
| Available inventory | quantity − reserved_quantity − unavailable_quantity; equals summed Shopify available |
| Inactive levels/locations | Preserved in snapshot but excluded from aggregate |
| Untracked inventory | No confirmed Inventory row; stock-dependent agents decline |
| Missing cost | Product.cost_price = null; never inferred from selling price |
| Orders | External order mapping to normal Order and current-quantity OrderItems |

Default local reorder settings for a new inventory row are 10/50; these are CartPilot
planning defaults, not facts supplied by Shopify. Existing merchant reorder settings
are preserved. No reservation quantities are invented. Negative/oversold or
non-reconciling stock is reported as an inventory failure. On a failed inventory
refresh, its prior Inventory row is removed and cost becomes unknown, preventing
stale stock appearing as confirmed sellable inventory. Successfully imported
independent records remain committed. The external mapping remains for a later retry.

Products keep source `shopify`; legacy/demo products default to `local`. The local
SKU stays stable after first import while the latest external SKU remains in metadata.
Titles are capped at 255 characters, categories at 100; absent product type maps to
`Uncategorized`. Source metadata supplies no unsupported listing attributes. The
selling price comes from the variant. Products stage alone clears cost until an
inventory/cost refresh confirms it. Product source dates and sync timestamps are
persisted. Synced prices do not fabricate local PriceHistory action records.

Orders use the external order ID as identity, not display number. Local order numbers
are prefixed `SHOPIFY-{connection ID}-{external numeric ID}`. `currentQuantity`
excludes refunded/removed units; zero current lines are omitted. The supplied
discounted unit price maps to local unit price and multiplied subtotal, each rounded
half up to two decimals. Shopify labels this unit amount approximate; repeating
decimal discounts are accepted. Subtotal rounds after multiplying the source amount
and can differ slightly from rounded local unit price times quantity. Order current
total remains the shop-currency total (it may include shipping/tax). No customer
email, name, address, phone or raw order payload is requested/persisted.

Status mapping:

- Cancelled, REFUNDED, VOIDED or EXPIRED → cancelled, excluded from sales evidence.
- FULFILLED → shipped; fulfillment alone does not establish delivery.
- Known unfulfilled/partial/on-hold states → confirmed for paid/partially-paid/
  partially-refunded orders, otherwise pending.
- Unknown financial/fulfillment states → cancelled and a visible partial-sync error.
- Any unmapped positive-quantity line → skip the whole order; invalidate an existing
  cached order's sales evidence rather than keep an outdated partial order.

Both products and orders have unique `(connection_id, external_id)` mapping
constraints. Repeat sync updates mapped rows and replaces order lines atomically;
no duplicated sales units. Product/variant and order upserts commit one independent
record at a time. Each inventory item imports only after all its locations have been
fetched. A persistent atomic busy flag blocks simultaneous sync of the same cache.
Last summary tracks started/completed/partial/failed and exact committed counts.
If there are failures and committed successes, status is partial; failures without
successes are failed. Warnings explain unavailable optional cost.

Root variant queries paginate every variant, including products with many variants.
Orders, nested order lines and inventory locations paginate independently with
advancing-cursor checks and configured bounds. HTTP 429/5xx and transient timeout/
network failures retry with bounded backoff. Numeric/date Retry-After and GraphQL
query-budget restoration are respected; waits above 60 seconds stop with a retry-later
error. Auth/permission errors do not retry, except optional cost permission fallback
repeats inventory reads without unitCost. Upstream response/error text, credentials
and customer payloads are never logged or returned. Redirects are not followed.

## API and UI

All routes use `/api/v1/integrations/shopify`:

- `GET /status?merchant_id=1`: test remote shop identity/scopes; non-secret connected,
  configured, store, currency, API version, message and last summary. Unconfigured or
  failed connections show a clean disconnected result.
- `POST /sync`: `{ "merchant_id": 1, "products": true, "inventory": true, "orders": true }`.
  Stage booleans default true. At least one must be selected. Returns a typed summary.
- `GET /last-sync?merchant_id=1`: persisted summary or null, no remote call.

For example, without exposing credentials:

```bash
curl 'http://localhost:8000/api/v1/integrations/shopify/status?merchant_id=1'
curl -X POST 'http://localhost:8000/api/v1/integrations/shopify/sync' \
  -H 'Content-Type: application/json' -d '{"merchant_id":1}'
curl 'http://localhost:8000/api/v1/integrations/shopify/last-sync?merchant_id=1'
```

The Integrations card displays READ ONLY, real connection/sync loading states, disabled
concurrent buttons, last sync, committed counts, skipped orders, errors and warnings.
A successful sync refreshes the local catalog. Product details identify Shopify/local
source and show missing cost/margin as unknown/unavailable. Actions and confirmation
state **Local/Simulated · Not synchronized to Shopify**. Set VITE_CURRENCY to match
the connected shop's currency; the integration card reports the source currency.

## Verification and demo

Run from backend:

```bash
venv/bin/python -m pytest
venv/bin/python -m tests.demo_shopify
```

Run from frontend: `npm test -- --run` and `npm run build`. Lint is not configured.
The [offline demo artifact](../docs/examples/shopify-demo.json) is generated through
mocked HTTP and an isolated in-memory database: three variants, multi-location stock,
first/repeat sync, all four normal agents, Balanced Growth and partial inventory failure.
It does not access a real store or change the developer database.

Manual live demo after credentials are configured: Integrations → Connected → READ
ONLY → Sync Now → summary → Products → Shopify product → Restock → Pricing → AI
Manager/Balanced Growth → unified recommendations. If optional cost is unavailable,
show the safe pricing/promotion decline. Review the fixed query registry/network calls
as evidence that only GraphQL reads were sent. For the failure demo, provide an invalid
or expired token in the backend environment, restart it, and Test Connection: a clean
failure appears while the original local/demo merchant remains usable.

Alembic upgrade preserves legacy rows, makes cost nullable, adds nonnegative
unavailable stock and the three identity tables. Downgrade refuses when unknown cost
or unavailable stock would make restoration lossy. Migrations are tested only on
isolated SQLite databases here; no user database migration was run.

## Known limitations / Phase 12 readiness

- Live store connection/sync needs developer credentials; tests use synthetic HTTP.
- One configured store/merchant per backend process; manual sync only, last-summary
  metadata rather than full history. API runs synchronously; large stores may outlast
  reverse-proxy request timeouts. There are no webhooks or unattended workers.
- No automated token refresh/OAuth, production identity, supplier/purchase integration,
  Shopify writes, FX conversion or fulfillment delivery inference.
- Model money is two-decimal Numeric(10,2). Unsupported precision/oversized source
  amounts are reported as invalid records instead of silently truncating monetary facts.
  Approximate discounted unit prices are explicitly rounded as described above.
- Root pagination is bounded (100 pages by default) and does not provide an atomic
  snapshot of a store changing during sync. Invalid source records report safe errors.
- Orders older than 59 days are outside this import window; previously imported rows
  remain cached. Deleted variants/products and older-order edits require reconciliation;
  absence from a read page is not treated as proof of deletion.
- Cache freshness is recorded, not guaranteed continuously. Optional partial-stage
  sync can leave independently dated sources. Read summary/timestamps before analysis.
- If the process crashes while syncing, its busy flag can remain set. After confirming
  no worker is running, a developer can reset `shopify_connections.sync_in_progress`
  for that connection in the local DB; automatic lease/worker recovery is future hardening.
- Existing Phase 9 human approval, current-state revalidation, idempotency and audits
  apply to local cache edits. Shopify refresh may invalidate previously approved data.

Phase 12 can validate live scopes/permissions and representative large catalogs, test
PostgreSQL migrations/concurrency, and harden authentication, job recovery, freshness,
observability and deployment. No Phase 12 implementation is included.

Verification: **72 Phase 11 backend tests; 434 total backend tests; 66 frontend
tests (9 Shopify UI tests); frontend production build passed.** Lint is not configured.
`git diff --check` passed. The integration/agent import review found no Shopify writes
or direct Shopify calls inside agents; repository-content scanning found no real
Shopify token. No commit was created; existing uncommitted prior-phase work was retained.
