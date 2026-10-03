# PHASE 07 — PROMOTION AGENT

Status: COMPLETE. Phase 8 has not been implemented.

The Promotion Agent generates recommendations only. No promotions are automatically
launched. No product prices, inventory, commerce actions, approvals or campaigns are
modified by the API or orchestrator. No LLM, migration, or new dependency is required.

## Inputs and shared analytics

The agent reads existing Product, Inventory, Order and OrderItem data. Existing pricing
analytics supply available inventory, cost/current price, recent units/revenue/orders,
lifetime order count, and sales velocity. The same non-cancelled, merchant-owned,
time-bounded unit query and velocity function are reused. Pending orders count as
observed demand, not settled revenue. Future and foreign-merchant orders are excluded.
Existing Restock calculations supply validated inventory and stockout/lead-time risk,
using the configured Restock lookback even if the Promotion lookback differs.

Product age provides the observation-window safeguard. Products younger than the
configured lookback hold price. Missing inventory, invalid reservations, negative
inventory parameters, nonpositive selling prices, or nonfinite/negative cost fail
validation rather than producing an unsafe discount. Inactive products hold price.
No sales history can still produce advice for an older, stocked product, with lower
confidence; age alone does not establish reliable sales-data collection.

## Deterministic decisions

Default lookback is 14 days. Trend compares newer seven days against preceding seven
using units/day. The shared total window includes both endpoints; the newer interval
excludes the split boundary and the older interval includes it, avoiding double counting.
Odd lookbacks split into floor(days/2) recent days and the remaining previous days;
rates account for unequal lengths. A change greater than 20% is increasing/declining;
otherwise stable. Previous zero and recent positive means increasing; both zero means
stable. Young products or no historical orders report insufficient_data.

Excess stock is more than 45 days of available inventory at current sales velocity.
Zero sales uses at least 30 available units and null days of inventory, with no division
by zero. Weak demand is below 1.5 units/day or a declining trend. Candidates must have
both excess stock and weak demand. Normal inventory or healthy demand holds price.

Block demand-stimulating promotions when available inventory is at or below the reorder
point, Restock risk is high, or stockout exposure exists. This uses existing unrounded
lead-time demand comparisons; supplier-arrival equality is protected.

Discount tiers: 5% for weak demand, 10% for declining demand, 15% for zero sales.
All thresholds/tiers are centralized in Settings and exposed in `.env.example`:

```text
PROMOTION_LOOKBACK_DAYS=14
MAX_PROMOTION_DISCOUNT_PERCENT=20
PROMOTION_MIN_MARGIN_PERCENT=10
HIGH_INVENTORY_DAYS_THRESHOLD=45
SLOW_SALES_THRESHOLD=1.5
PROMOTION_ZERO_SALES_MIN_INVENTORY=30
PROMOTION_TREND_CHANGE_PERCENT=20
PROMOTION_MILD_DISCOUNT_PERCENT=5
PROMOTION_MODERATE_DISCOUNT_PERCENT=10
PROMOTION_SEVERE_DISCOUNT_PERCENT=15
```

Gross margin = (price − cost) / price × 100. Retained margin uses promotional price.
Promotion's minimum is **gross margin**, distinct from the existing Pricing Agent's
`MIN_MARGIN_PERCENT` markup on cost; that pricing behavior remains unchanged.
The floor is cost / (1 − retained-margin-percent/100). Maximum discount and the margin
floor reduce the proposed percentage, rounded DOWN to two decimals. Promotional price
uses Decimal and rounds half-up to cents. If cent rounding would breach the floor or
produce no price reduction, the promotion is blocked. Hard safety rules are never
replaced by a high-risk label. A no-promotion output has type none, zero discount, and
exactly the current price. Schema validation enforces flag/type/discount/price coherence.

Confidence is a reproducible heuristic: 0.20 for a young product or 0.40 for a full age
window, plus 0.20 for at least three lifetime orders (0.10 for fewer positive orders),
plus 0.15 for declining demand; capped at 0.90. It is not accuracy or a calibrated
probability. Risk is high for inventory blocking, insufficient observation history,
margin blocking or margin-limited discounts; medium for discounts >=10% or fewer than
three historical orders; otherwise low. Expected effect uses qualified sell-through
language and never guarantees revenue lift.

## API and persistence

`POST /api/v1/promotion/recommend` accepts strict positive `product_id`; optional
`merchant_id` validates ownership. The frontend always supplies merchant_id.
Unknown product: 404; foreign product: 403; invalid inventory/money/input: 422;
SQLAlchemy failures: sanitized 503. Insufficient history returns a structured hold.
These scope checks do not implement authenticated identity binding.

Real isolated-demo request and response (full output is in
[the recorded API demo](../docs/examples/promotion-demo.json)):

```json
{"product_id": 2, "merchant_id": 1}
```

```json
{
  "product_id": 2,
  "current_price": 1499,
  "cost_price": 850,
  "promotion_recommended": true,
  "promotion_type": "discount",
  "discount_percentage": 10,
  "promotional_price": 1349.1,
  "reason": "High available inventory combined with weak or declining sales suggests a controlled discount to improve sell-through.",
  "confidence": 0.75,
  "risk_level": "medium",
  "available_inventory": 120,
  "sales_velocity": 1.2142857142857142,
  "sales_trend": "declining"
}
```

The frozen typed response additionally includes gross and retained margin, recent and
previous interval units, inventory days, and expected effect. API and context reads
suppress autoflush; they never persist proposals. A separate promotion persistence
service follows previous phases: stage a pending Recommendation of type promotion,
flush, and leave commit/rollback to the caller. Repeated explicit saves can create new
records, as with existing agents; recommendation endpoints create none. Saved read
APIs and frontend cards support typed promotion payloads.

## Orchestrator

Existing six goal routes retain their behavior. New deterministic routes:

| Goal | Agents |
| --- | --- |
| move slow inventory | Promotion |
| increase sell-through | Promotion |
| reduce excess inventory | Promotion |
| improve revenue from slow-moving products | Promotion |
| increase revenue while maintaining healthy inventory | Pricing + Restock + Promotion |

The combined route evaluates promotion eligibility for each explicitly selected
product and returns a hold when unsafe or unnecessary. It is not added to every goal.
Shared context caches equal lookbacks; promotion's trend query adds only the newer
interval. Missing inventory fails that specialist without discarding successful agents.
Request `constraints.max_promotion_discount_percent` may tighten the global maximum;
it cannot loosen it. The orchestrator independently revalidates promotion output,
snapshot identity, margin, discount cap, and inventory guardrails.

`promotion_inventory_conflict` defers demand stimulation when a returned promotion
meets a high-risk restock result. `pricing_promotion_conflict` defers promotion when a
base-price increase or decrease is also proposed; this prevents conflicting prices and
stacked discounts. A pricing hold and controlled promotion are compatible and explained.
Stockout-critical inventory remains first, pricing opportunities medium, promotions
low. Deferred coordinated prices hold the current price and use no_promotion; original
proposals remain visible. Failed restock analysis also defers an otherwise proposed
promotion. Overall confidence/risk and approval-required behavior remain unchanged.
Naturally unsafe promotions are blocked by the agent before conflicts arise; tests
inject conflicting advisory outputs to verify defensive coordination independently.

## Frontend and manual demo

PromotionCard shows discount/hold, current/promotional price, inventory, velocity,
trend, retained margin, reason, expected effect, risk, confidence and Recommendation
Only. Product drawer adds Run Promotion Analysis. Recommendations supports promotion
filters, saved payloads and session results. AI Manager offers the new goals and displays
promotion results/conflicts/deferred steps. Agent Activity shows four active agents;
Listing alone remains Coming Soon. There are no launch/apply/publish controls.

Run the application as documented in README. Choose an existing product with a full
history window, high inventory, declining/weak sales and sufficient margin; its product
ID depends on your database. Freshly seeded product timestamps can cause safe holds
until the observation window is sufficient. The recorded demo uses an isolated SQLite
fixture, not a production merchant: a 60-day-old Bluetooth Speaker, price 1499, cost
850, 120 available units, previous seven-day sales 16 and recent sales 1. It returns
10%, promotional price 1349.10, medium risk, confidence 75%, retained margin 37.0%.
Frontend currency defaults to USD as in Phase 6; VITE_CURRENCY=INR changes presentation
only, without conversion.

For a combined goal, select a high-demand low-stock product and the speaker. The demo
returned a 67-unit critical restock proposal and bounded price increase for the first
product, blocked its promotion, and proposed the speaker's 10% discount with base-price
hold. Six results were complete, overall risk high, confidence 40%, approval required.
No actions ran. This is recorded in the API demo JSON for review.

## Verification

```bash
cd backend
venv/bin/python -m pytest tests/test_promotion.py -q
venv/bin/python -m pytest tests/test_promotion_orchestration.py tests/test_orchestrator.py tests/test_orchestration_rules.py tests/test_orchestration_api.py -q
venv/bin/python -m pytest -q
cd ../frontend
npm test -- --run
npm run build
```

Promotion tests: 39. Orchestrator tests: 68 (52 existing + 16 new). Total backend: 240
passed. Frontend: 31 passed. TypeScript/Vite production build passed. No lint script
is configured. Existing Phase 1–6 tests remain passing.

Chrome verified actual promotion API/loading, product analysis, combined-agent plan,
recommendation session results, active-agent UI, and responsive recommendations at
1024/768/390px without page overflow. Desktop/mobile screenshots visually inspected;
no unexpected console errors or failed HTTP requests. Demo backend was isolated
in-memory SQLite; production PostgreSQL data was not changed. Temporary demo servers
were stopped after verification.

## Limitations and Phase 8 readiness

Simple discount proposals only. No segmentation, elasticity model, campaign duration,
coupons, bundles, advertising, email, real execution, or Listing Agent. Trend does not
correct for seasonality or past stockouts; product age is a conservative proxy for
observation history. Supplier timing remains global. No merchant policy table exists;
global defaults and tightened request constraints govern discounts. Authentication,
approvals and execution remain future work. Session history remains memory-only.

Typed specialist contracts, shared context, coordination rules and reusable UI cards
are ready for a later Listing Agent. Phase 8 is not implemented.
