# PHASE 03 — PRICING AGENT

## Objective

Build the Pricing Agent.

## Inputs

product
price
cost
inventory
sales velocity
historical sales

## Responsibilities

Detect:

high demand
low inventory
slow sales
pricing opportunities

## Output

Structured PricingRecommendation.

Fields:

product_id
current_price
recommended_price
reason
confidence
risk_level

## Rules

Never recommend below cost.

Never exceed configured maximum price increase.

Never exceed configured maximum price decrease.

## Testing

Test:

high demand
low demand
low inventory
high inventory
boundary prices
below-cost protection

## Important

Agent produces recommendations only.

No automatic price changes.
---

## Phase 3 — Pricing Agent

Status: COMPLETE. Deterministic, recommendation-only backend; no LLM or storefront integration.
**Pricing Agent does NOT automatically change prices.** Inventory, orders, approvals,
and price history are unchanged by recommendation generation.

### API

`POST /api/v1/pricing/recommend`

Request:
```json
{"product_id": 12}
```
Illustrative response (values depend on stored data):
```json
{
  "product_id": 12,
  "current_price": 100.0,
  "recommended_price": 105.0,
  "reason": "Strong sales velocity supported by healthy inventory levels indicates strong demand. Recommending a controlled price increase.",
  "confidence": 0.8,
  "risk_level": "medium",
  "price_change_percent": 5.0,
  "sales_velocity": 1.2857142857142858,
  "inventory_quantity": 55,
  "cost_price": 40.0
}
```
Positive integer product IDs are required. Missing products return 404. Invalid prices
or incompatible safety limits return 422. Missing inventory holds the current price,
with confidence 0.20 and high risk, subject to the cost floor and price limits.

### Inputs and signals

Uses existing Product, Inventory, Order/OrderItem, and PriceHistory tables.
The read service lives in `app/services/pricing/signals.py`; Phase 2 has no separate
repository package, so queries remain in this service. No database migration is needed.

- Sales velocity = non-cancelled units sold / `PRICING_LOOKBACK_DAYS` (default 14).
  The window includes its boundaries; future orders are excluded. Orders must belong
  to the product's merchant. Pending orders count as demand signals, not settled sales.
  Unit totals, distinct orders, revenue, lifetime order count, and price-history count
  are also gathered. An optional `as_of` time supports reproducible snapshot analysis.
- Available inventory = max(0, quantity - reserved quantity). Low stock is at or below
  reorder point. Days of inventory = available units / unrounded sales velocity.
  With zero velocity, 999 days is a documented classification sentinel for stocked items.
- Strong sales: at least 1 unit/day OR 10 units during lookback. Weak sales: below
  0.25 units/day OR at most 2 units during lookback, with sufficient history.
- Healthy inventory: above reorder point and at most 45 days of stock. High inventory:
  above reorder point + 1.5 × reorder quantity OR over 45 days of stock. These signals
  may overlap; strong-sales rules take precedence. Thresholds are named constants
  in `signals.py`.
- Sufficient history: at least 3 lifetime non-cancelled orders OR 3 recent units,
  plus inventory availability. This is a heuristic, not evidence of demand elasticity.

### Decisions and guardrails

Strong sales with low or healthy inventory proposes a 5% increase. Weak sales with
high inventory proposes a 5% decrease. Other cases hold price. Low stock never triggers
a discount. Insufficient data holds price with low confidence and high risk.

Environment settings (also in `.env.example`):
```text
MAX_PRICE_INCREASE_PERCENT=10.0
MAX_PRICE_DECREASE_PERCENT=10.0
PRICING_LOOKBACK_DAYS=14
MIN_MARGIN_PERCENT=0.0
PRICING_ADJUSTMENT_PERCENT=5.0
```
Settings reject nonfinite/negative limits, zero lookback, and decreases or adjustments
of 100% or greater. The optional minimum margin is a **markup on cost**, calculated
as cost × (1 + percentage/100), not a gross-margin percentage.

Price proposals use Decimal arithmetic. Increase ceilings round down to cents;
decrease and cost floors round up to cents. The final price must satisfy both the cost
floor and configured change limits. If these cannot coexist, generation fails with 422
rather than overriding a guardrail. Nonpositive selling prices and nonfinite or negative
costs are rejected. The typed, frozen response validates finite metrics, confidence,
risk enum, positive prices, and below-cost protection.

### Confidence and risk

Confidence is deterministic and **not a statistically calibrated probability**:
insufficient data gives 0.20; otherwise start at 0.35, add 0.25 for at least 15 recent
orders (or 0.15 for at least 5), 0.15 for positive inventory, 0.10 for price-history
availability, and 0.15 for velocity at least 0.5 units/day. Round to two decimals and
bound to [0.10, 1.00]. These measure signal availability and volume, not sales consistency.

Risk is high for insufficient data, low stock, cost-floor clamping, or gross margin
below 5%. Otherwise a capped proposal or price change of at least 5% is medium risk;
remaining cases are low risk. Risk values are restricted to low/medium/high.

### Boundaries and optional persistence

`PricingAgent.analyze()` reads data and returns a recommendation without writes.
`generate_and_persist_recommendation()` in `services/pricing/persistence.py` is a separate
application service that stages a **pending** Recommendation using the existing model.
It flushes; the caller owns commit/rollback. The API does not persist proposals.
Neither path approves or executes recommendations. Phase 4 may reuse the sales and
inventory signals for restock proposals; approval, execution, orchestration, and external
store APIs remain future work.

### Verification

```bash
cd backend
venv/bin/python -m pytest -q
venv/bin/python -m pytest tests/test_pricing_agent.py tests/test_pricing_rules.py tests/test_pricing_api.py -q
cd ../frontend
npm test -- --run
npm run build
```
