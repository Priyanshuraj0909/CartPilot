# API, data model and security reference

## Actual routes

Except root routes, prefix is `/api/v1`. OpenAPI at `/docs` is the detailed schema reference.

| Method | Path after prefix | Purpose |
| --- | --- | --- |
| GET | /health; /health/detailed | Liveness; sanitized DB/optional Redis diagnostics |
| GET | /merchants | Available merchant summaries |
| GET | /products?merchant_id=ID | Paginated catalog, bounds and analytics |
| GET | /inventory?merchant_id=ID | Current catalog inventory view |
| GET | /recommendations?merchant_id=ID | Persisted saved recommendations |
| POST | /pricing/recommend | PricingRequest → PricingRecommendation |
| POST | /restock/recommend | RestockRequest → RestockRecommendation |
| POST | /promotion/recommend | PromotionRequest → PromotionRecommendation |
| POST | /listing/recommend | ListingRequest → ListingRecommendation |
| POST | /orchestrate | Merchant goal/product scope → advisory ActionPlan |
| POST / GET | /actions | Create typed guarded proposal / list merchant actions |
| GET | /actions/{id}?merchant_id=ID | Scoped action detail |
| POST | /actions/{id}/approve; /reject | Human decision; no execution |
| POST | /actions/{id}/execute | Separate confirmed execution/revalidation |
| GET | /action-history?merchant_id=ID | Persistent audit events |
| GET | /integrations/shopify/status; /last-sync | Connection and last synchronization summary; merchant_id query required |
| POST | /integrations/shopify/sync | Manual bounded read-only import |

Root `GET /health` returns {status:ok}; root `/` returns app metadata.
Specialist requests include product_id and frontend-supplied merchant_id; legacy pricing/
restock and other single-product contracts permit optional scope for compatibility.
Orchestrator requires merchant scope. Typed schemas reject invalid/unknown fields and
bound quantities/limits. No endpoint executes a recommendation during analysis.
Action writes and all Shopify routes are development/test only, 403 in production.
There is no public reset, supplier-order, Shopify-write or AgentRun-history API.

## Data model map

| Entity | Main responsibility |
| --- | --- |
| Merchant | Store identity and ownership; not an authenticated login principal |
| Product | SKU/name/category/description, cost/selling price, status, local/Shopify source |
| Inventory | Physical/reserved/unavailable quantities and reorder thresholds; one product association |
| Order / OrderItem | Merchant-scoped sales and product-level quantities/prices |
| PriceHistory | Product price changes and change metadata |
| AgentRun | Run/status model exists; current session UI is not persisted through it |
| Recommendation | Structured agent proposal and optional saved history |
| Action | Immutable execution payload, status, workflow identity, policy/result and timestamps |
| Approval | Human decision records associated with actions |
| AuditLog | Persistent workflow events and safe before/after execution metadata |
| ShopifyConnection | Bound store/merchant identity, locations and sync status; no token storage |
| ExternalProductMapping | Shopify product/variant → local product identity, source/location metadata |
| ExternalOrderMapping | Shopify order → local order identity for idempotent sync |

Foreign keys/relationships enforce ownership and associated-record integrity; SQLite
foreign keys are enabled in tests/app. Unique external/workflow identities prevent
accidental duplicates. Prices use Decimal/Numeric(10,2); timestamps are normalized UTC.
Alembic has three current revisions, ending at `11shopify_read_only`. Migrations and
explicit demo seed are separate from the serving process. Read source models/migrations
for exact fields rather than treating this summary as a complete schema export.

## Security and guarded execution

Environment-managed backend credentials; VITE_ settings are public and contain no
Shopify/DB secrets. Closed read-only Shopify GraphQL registry, no mutation dispatcher
or redirects, bounded timeout/retries/pagination. Shopify remains the source of truth;
local action results are not synchronized to it.

Scoped merchant-product/action/recommendation ownership checks protect accidental
cross-store access, but **there is no authenticated identity binding**. CORS controls
browser origin access, not merchant authentication. Legacy omitted scope and unauthenticated
read APIs make trusted local/private access essential. Production keeps write routes
blocked; do not weaken that gate for a demonstration.

Workflow: validated immutable proposal → policy checks → awaiting human approval →
review decision → separate execution confirmation → atomic claim and fresh validation
→ local mutation/simulation → audit. Policies check current price/cost, margin, quantity,
stockout/inventory context, source listing facts and approval state. Idempotency,
transactions/savepoints, rollback, source comparisons and PostgreSQL locking mechanisms
protect execution. Basic PostgreSQL execution passed; locking stress has not been measured.

Failure messages/logs are sanitized; debug is false. No credentials are persisted in
integration mappings or returned to the frontend. Inventory gaps/unknown cost fail safely.
Public production would require authentication/authorization, ingress rate controls,
provider HTTPS/TLS/backups and broader concurrency verification. No compliance guarantee
or audited enterprise security claim is made.
