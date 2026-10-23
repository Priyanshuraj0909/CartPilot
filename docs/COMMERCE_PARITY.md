# Commerce capability parity checklist

Reference: public VishalDhariwal/CartPilot source, reviewed 23 October 2026. This tracks
functional equivalents, not copied code or claimed live-provider validation.

| Capability | Current work |
| --- | --- |
| Conversational shopping and saved sessions | Implemented: grounded multi-item drafts, follow-ups, removal, bounded history, clear and reload restoration |
| Edit/revise cart, substitutes, upsells | Implemented: fresh server-priced drafts reset approval; budget-checked suggestions and recorded upsell selection |
| Payment reconciliation/recovery | Implemented: authoritative provider reads, unknown-result claims, fresh recovery draft and single-use shopper review link |
| Cancellation/full and partial refunds | Implemented for simulation/Razorpay test mode, with captured-balance/idempotency guards; separate merchant return review/approval/receipt |
| Category compatibility and growth-rule management | Implemented: provider-generated reviewable suggestions or observed-order fallback; manual pair CRUD, rule creation/mute/delete and campaign windows |
| Ranking preview, co-purchase lift and attribution | Implemented: baseline/hybrid comparison, observed associations and labeled selection/test-payment metrics; no causal revenue claim |
| Scheduled growth and contextual merchandising | Implemented worker/controls; date/season-aware ranking rules, optional weather and merchant-specified upcoming campaigns |
| CSV/API/demo onboarding | Implemented: atomic CSV, bounded DummyJSON/configured API import, demo seed and local catalog archive preserving history |
| Provider failover/local embeddings/64D Item2Vec | Implemented: optional OpenAI/Gemini structured failover, explicit 64D training, optional local MiniLM or Gemini semantic index |
| MCP workflows/browser handoff | Implemented: expanded shopping/growth tools; financial actions hand off to browser confirmation |

All financial actions require deterministic validation and explicit confirmation.
Synthetic/test activity must remain visibly separate from real revenue.

## Try the full workflow

1. Run `cd backend && venv/bin/python -m alembic upgrade head`, then start the normal
   backend/frontend. Sign in and open Growth Console → Commerce Studio.
2. Seed the six-product demo, import CSV, import DummyJSON, or configure a supplier.
   Set publication explicitly before sharing `/shop/YOUR_MERCHANT_ID`.
3. In the storefront, open **Chat with CartPilot · saved carts**. Try
   `add a mouse and a journal under ₹2,000`. Each line and the full budget are validated.
   Follow-up discovery, removal and replacements create/review drafts; chat cannot pay.
4. Review the draft, approve, and separately confirm simulation or a configured test
   payment. **Edit cart quantities**, upsells and substitutes create new drafts and
   require approval again. A zero quantity removes a line; empty carts are rejected.
5. Open **Recovery, cancellation & refunds**, review eligibility, select the explicit
   confirmation checkbox and choose the operation. Partial/full refunds use integer
   paise; successful refunds cannot exceed the captured amount. Razorpay test refunds
   require at least INR 1.00; local simulations support paise boundaries.
6. A return request creates a separate review. The merchant can approve/reject and
   mark receipt in Transaction Ledger; none of these steps automatically refunds or
   changes inventory. A refund remains a separate confirmed operation.
7. Saved chat/carts are restored from the current browser tab's sessionStorage token
   and server records. Shopper capabilities expire after one hour; this is not a
   permanent buyer account. Initialization is deduplicated under React StrictMode.

## Recovery and uncertain provider outcomes

Recovery closes an unpaid test link when necessary, refreshes stock/prices and creates
a new draft; a shopper must approve and confirm checkout again. Growth Console's
Transaction Ledger lets the store owner prepare a recovery review link. The URL
fragment holds a five-minute single-use capability: share it only with the intended
shopper. Redemption transfers the cart to the receiving shopper session and binds
against the source owner so older grants cannot take it back.

Merchant recovery rules can propose discounts up to the configured cap (hard maximum
20%). Known cost, inventory above reorder point and retained-margin checks are required.
The resulting price is the greater of the discounted cent price and the cost-based
margin floor rounded upward. Acceptance creates a quote, not a catalog price change.
Current prices, cost, stock and policy are rechecked at approval/checkout. Repeated
offer acceptance with the same key returns the same draft; offers do not compound.

An external-operation request is durably claimed before contacting Razorpay. A timeout
does not prove failure. **Reconcile provider status** checks existing links/payments/
refunds and updates the recorded state; pending claims block another financial action.
Do not substitute a new request key after uncertainty. The frontend retains the key
for retries during the current action panel. Claims and refund balances are protected
by PostgreSQL row locks; concurrent full refunds and offer acceptance have dedicated tests.

For an uncertain link creation without a stored ID, reconciliation inspects up to 100
provider links for an exact cart reference; missing/ambiguous matches require manual
provider review. Refund reconciliation similarly bounds lookup and never repeats the
refund POST. Live credentials/financial operation were not used in verification.

## Merchant growth, compatibility and context

Commerce Studio supports category compatibility overrides and reviewable suggestions.
Optional AI receives only current category names; unknown categories are filtered.
Without a valid provider response, completed-order associations provide suggestions.
Suggestions are not saved until merchant review. Compatibility scores have their own
explanation and are never presented as invented co-purchase counts.

Growth rules select category features, recovery offers or seasonal features. Rules can
be muted/deleted and constrained by season and an inclusive-start/exclusive-end time
window. Campaign/festival names/dates are merchant inputs, not an invented holiday
calendar. Upcoming dated campaigns appear in context. The season label is an India
monthly heuristic; optional current weather is read from Open-Meteo using configured
coordinates and gracefully degrades when unavailable.

Each growth cycle applies at most two configured in-stock ranking features. It does
not autonomously charge, refund, change catalog prices or launch promotions. To run
scheduled cycles, enable the merchant control and host a persistent process:

```bash
cd backend
venv/bin/python -m app.services.commerce.worker
```

The worker checks every 30 seconds; database due-time claims prevent duplicate cycles.
It must run outside short-lived Vercel request handlers. Worker hosting is not
automatically provisioned by a GitHub push. Recovery insights do not send email/SMS;
review links can be shared manually.

Ranking preview compares the same current catalog/budget against baseline and hybrid
ranking. Observed lift is `joint_order_count × sampled_orders / (orders_with_A × orders_with_B)`
over up to 500 recent completed orders (20 unique items/order). This is association,
not a causal A/B test. Attribution reports recorded selections and test-paid upsell
value separately; real incremental revenue is unknown, not a fabricated number.

## Providers and onboarding

Existing Gemini and Razorpay test settings remain supported. Optional backend settings:

```ini
OPENAI_API_KEY=your-own-key
BUYER_AI_PRIMARY=gemini
BUYER_OPENAI_MODEL=gpt-4.1-mini
BUYER_LOCAL_EMBEDDINGS=false
COMMERCE_CATALOG_API_URL=https://your-supplier.example/products
COMMERCE_CATALOG_API_TOKEN=your-own-bearer-token
COMMERCE_WEATHER_ENABLED=false
COMMERCE_WEATHER_LATITUDE=12.97
COMMERCE_WEATHER_LONGITUDE=77.59
```

`BUYER_AI_ENABLED=true` enables configured providers in preferred/fallback order.
Each structured call is bounded to eight seconds/provider; Pydantic validates the
output, and explicit parsed budgets retain precedence. Both-provider failure uses
local intent/association fallback. No mutation tools or database connection are
passed to either model. OpenAI uses Responses structured output with `store=false`.
See [official OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs).

Item2Vec now trains 64-dimensional vectors with the existing bounded skip-gram engine;
training remains explicit and experimental. For optional local 384D MiniLM embeddings:

```bash
cd backend
venv/bin/pip install -r requirements-ml.txt
```

Set `BUYER_LOCAL_EMBEDDINGS=true` and `BUYER_SEMANTIC_ENABLED=true`, then index the
catalog. Local weights require a suitable persistent machine and initial model download;
they are not bundled into the lightweight hosted API. Gemini semantic indexing remains
available. Index identity includes the backend/model and text fingerprints, preventing
mixing vectors or silently using changed product descriptions. Local/model/provider
paths are covered by mocks; actual local-weight/provider operation remains unverified.

API onboarding accepts up to 100 complete products and 2 MB from a fixed demo source
or an owner-configured HTTPS endpoint. Configured URLs reject embedded credentials,
private addresses and query strings; redirects are not followed. Tokens are backend
Bearer headers. Expected JSON is an array or `{products: [...]}` with `id`/`sku`,
`title`/`name`, `category`, `price`, `stock`, optional `description`. Existing SKUs are
skipped, invalid batches write nothing, and unknown supplier costs remain NULL.
Verify supplier currency/costs before publishing INR prices or running margin-sensitive
actions. Archiving local products preserves orders/history and excludes Shopify data.

## MCP and discovery

The existing stdio configuration works unchanged. Tools now include search/product,
draft proposal/status/audit, upsells, item addition, recovery-offer check, buyer journey,
payment status, checkout/cancel handoff, and scoped merchant growth opportunities/
metrics/actions. Merchant tools require the owner's account token in the server's
environment; shopper tokens cannot access merchant APIs.

`checkout` and `cancel_order` return eligibility plus a one-use browser review path.
They do not approve or execute financial actions from model arguments. Open the path
under the storefront origin to review and explicitly confirm. This provides practical
agent/browser continuity while preserving the repository's authorization boundary.
`/llms.txt` and `/.well-known/ucp` expose discovery metadata; external UCP conformance
or desktop MCP-client interoperability is not claimed.

## Verification

See [test summary](../TEST_SUMMARY.md), [browser evidence](examples/commerce-workflows-browser.json)
and [Phase 18](../phases/PHASE_18.md). Tests cover happy paths, invalid input, boundaries,
ownership, pending operations, model/provider failure, session races and concurrency.
Real provider credentials, permanent buyer identity, real stock fulfillment, external
notification delivery, worker hosting and production load remain outside verified scope.
