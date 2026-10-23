# Buyer commerce — Phase 17

CartPilot now combines its merchant decision-support workspace with a buyer shopping
experience. This is an original implementation in the existing stack. It does not
copy the referenced friend's source or claim identical algorithms or production readiness.

## Try the complete offline workflow

1. Run the normal backend migration (`cd backend && venv/bin/python -m alembic upgrade head`),
   backend and frontend. The new revision is `17_commerce`.
2. Sign up or sign in. Open **Growth Console**. Commerce management always requires
   an account, even when anonymous merchant analysis is allowed in development.
3. Import [commerce-catalog.csv](examples/commerce-catalog.csv), or use Manage Store
   to create products. CSV accepts at most 500 rows/1,000,000 characters with the exact
   template headers. Prices must cover explicit costs. Existing/duplicate SKUs and
   invalid rows reject the entire import; existing prices/stock are never overwritten.
4. Open **Buyer Storefront** for a private account preview. To share the public
   `/shop/YOUR_MERCHANT_ID` URL, explicitly enable **Publish public storefront** and save.
   Publication reveals names, descriptions, categories, prices and available stock.
5. Search naturally, e.g. `mouse under ₹1,000`. Choose quantities, then **Review
   server-priced cart**. Review the lines and total; **Approve this cart**.
6. Separately select **Confirm simulation**. Inspect the verified cart audit chain.
   No money moves, order is placed or physical inventory changes.

Amounts are INR, stored/calculated as integer paise. Existing merchant data has no
currency metadata; publish only catalogs whose numeric prices represent INR. No FX
conversion is performed. The storefront uses neutral illustrations because the
existing product schema does not contain verified product image URLs.

Shopper sessions expire after one hour; carts after 15 minutes. The browser holds
the shopper capability in component memory, so refreshing starts a new shopper
session and does not recover old carts. This currently limits recovery to the active
session. Unpublishing stops new public sessions; existing capabilities remain valid
until expiry. Growth insights list at most 50 active draft/approved carts idle for
five minutes. No recovery email/SMS or automatic discount is sent.

## Discovery and models

Ranking has four groups of signals:

| Signal | Behavior |
| --- | --- |
| Category relevance | Deterministic search/anchor category match; no LLM-generated compatibility graph |
| Behavioral | Completed-order co-purchase counts; optional explicit Item2Vec training |
| Text relevance | Local lexical matching; optional indexed Gemini dense semantic similarity |
| Business gates | Active catalog, available stock, blocked categories, spend/budget checks and transparent 1.35× featured-product boost |

Ranking orders by descending score, then ascending price and product ID, and returns
at most 24 products from the first 500 active priced products. Catalog truncation is
visible. Categories are case-insensitive exact policy matches. Hard filters always
precede merchant boosts or learned similarity. Search budget is the minimum of the
explicit UI amount, parsed request budget and merchant cap. A model never supplies
prices or quantities to the cart.

Item2Vec uses 16-dimensional skip-gram with two negative samples and three epochs,
seed 17, learning rate .035. It requires 30 completed multi-product orders and bounds
input to 500 recent completed orders, 20 distinct items/order, 500 products and 20,000
training pairs. It runs in a worker thread after an explicit merchant click; no new
package is needed. Simulations/test checkouts never enter training data. Historical
seeded/imported completed orders can enter training, so trained output does not
establish real customer behavior or measured lift. No automated retraining occurs.

Optional providers, configured **backend-side** in `.env`:

```ini
BUYER_AI_ENABLED=true
GEMINI_API_KEY=your-own-key
BUYER_GEMINI_MODEL=gemini-2.5-flash
BUYER_SEMANTIC_ENABLED=true
BUYER_EMBEDDING_MODEL=gemini-embedding-001
```

Structured intent has a 12-second timeout and validates the returned JSON. An explicit
locally parsed budget overrides the model budget. Model/provider errors use local
search. Search sends the shopper's query to Gemini only when enabled. No account
email, cart identity or cost data is sent for intent extraction.

**Index semantic catalog** sends product names/categories/descriptions to the configured
Gemini embedding endpoint. It indexes at most 50 changed documents/click, concurrency
four; repeat to finish a larger catalog. Failed batches retain the previous index.
The index records model identity and text fingerprints. Changed products are excluded
from semantic scoring until reindexed. Query embeddings use the same model; failures
fall back to other signals. The current adapter uses the `gemini-embedding-001`
task-type API and 768-dimensional vectors; switching to another API family requires
adapter validation. Optional model calls can incur provider charges.

## Razorpay test configuration

```ini
BUYER_RAZORPAY_TEST_ENABLED=true
RAZORPAY_KEY_ID=rzp_test_your-key
RAZORPAY_KEY_SECRET=your-own-test-secret
RAZORPAY_WEBHOOK_SECRET=your-own-test-webhook-secret
```

Configure the test dashboard webhook URL as
`https://YOUR_API/api/v1/commerce/webhooks/razorpay`, event `payment_link.paid`.
Only `rzp_test_` keys are accepted. Missing credentials preserve the approved cart
and return 503. No automatic fallback presents a simulated transaction as a payment.

The application posts a standard INR payment link with partial payments/reminders
disabled and a cart reference. A confirmed test checkout starts a separate 20-minute
payment window, meeting the provider's minimum 15-minute link-expiry requirement.
The initial quote still must be approved/confirmed within its original 15 minutes. Browser return URLs do not mark
payments paid. The webhook verifies HMAC-SHA256 over the raw body and checks link ID,
reference, currency, full amount and status. Repeated verified settlement is idempotent.
Verified payments are labeled `test_paid` and stay outside merchant sales/revenue.

`checkout_pending` means a request was claimed before contacting the provider. A
timeout may have created a link; retries do not create another. Review the test
dashboard using the cart UUID. There is no automatic reconciliation UI yet, and a
webhook arriving before the link ID is persisted requires provider retry. Provider availability/validation can still reject a request; review the first
request before building a fresh cart. Refunds, live charges, stock reservations and fulfillment are not
implemented. Real credentials/provider calls were not used in local verification.

## MCP stdio

The small adapter uses newline-delimited JSON-RPC, protocol `2025-06-18`, and the
existing HTTP API. In a compatible desktop client's MCP configuration:

```json
{
  "mcpServers": {
    "cartpilot": {
      "command": "/absolute/path/CartPilot/backend/venv/bin/python",
      "args": ["/absolute/path/CartPilot/backend/mcp_server.py"],
      "env": {
        "CARTPILOT_API_URL": "http://127.0.0.1:8000",
        "CARTPILOT_MERCHANT_ID": "1"
      }
    }
  }
}
```

The store must be published. A private owner preview may additionally supply a
short-lived `CARTPILOT_ACCOUNT_TOKEN` through the owner's local environment; never
commit tokens/configurations containing them. Remote URLs require HTTPS. The adapter
starts an isolated shopper session and exposes `search_catalog`, `get_product`,
`propose_cart`, `get_cart`, `get_order_audit_trail`. It has no direct database access
and no approve/checkout tools; it cannot autonomously purchase. Adapter-created draft
carts are not currently handed off to the browser's independent session. Protocol
unit tests pass; Claude Desktop/Cursor interoperability remains unverified.

## Verification and boundaries

See [test summary](../TEST_SUMMARY.md), [browser evidence](examples/commerce-browser.json)
and [screenshots](screenshots/README.md). Optional provider paths use mock transports.
PostgreSQL concurrency tests target only a disposable database named `cartpilot_ci`.
No live merchant data, payment provider or model API is needed for the default tests.

The per-cart audit is SHA-256 linked, not signed or externally anchored. It detects
inconsistent edits but does not prevent a privileged writer from replacing a chain.
Public ingress, broader load/abuse testing, data retention/cleanup, durable shopper
identity/recovery, real provider validation and production payment lifecycle design
remain future work. No revenue attribution, A/B lift or production readiness is claimed.

Provider references: [Gemini structured output](https://ai.google.dev/gemini-api/docs/structured-output),
[Gemini embeddings](https://ai.google.dev/gemini-api/docs/embeddings),
[Razorpay payment links](https://razorpay.com/docs/api/payments/payment-links/create-standard/),
[webhook signatures](https://razorpay.com/docs/webhooks/validate-test/),
[MCP stdio](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports).
