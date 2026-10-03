# PHASE 04 — RESTOCK AGENT

## Objective

Build the Restock Agent.

## Inputs

inventory
sales velocity
historical orders
reorder point
lead time

## Outputs

RestockRecommendation

Fields:

product_id
current_inventory
estimated_daily_sales
estimated_days_remaining
recommended_quantity
reason
confidence
risk_level

## Detection

Identify products likely to stock out.

## Safety

Never recommend negative quantity.

Respect maximum reorder quantity.

## Testing

Test:

healthy inventory
low inventory
high velocity
low velocity
zero sales
stockout scenario
---

## Implemented behavior

Status: COMPLETE — Phase 4 only.

**The Restock Agent does NOT place purchase orders or modify inventory automatically.**
It is independently callable, deterministic, and recommendation-only. No LLM,
Master Orchestrator, supplier integration, or dashboard changes are included.

### Inputs and shared analytics

`RestockAgent.analyze(product_id, session, as_of=None)` reads existing Product,
Inventory, Order, and OrderItem data through a restock signal service that adapts
Phase 3's read service. No new tables or dependencies are needed.

Sales velocity is non-cancelled units sold in the inclusive lookback window divided
by lookback days, default 14. Future orders and other merchants' orders are excluded;
pending orders are included as demand signals, consistently with pricing. Optional
`as_of` enables repeatable snapshots. Recent distinct orders and lifetime history
support the existing sufficiency heuristic: at least 3 lifetime orders OR 3 recent units.

Available stock follows `Inventory.available_quantity`: physical quantity minus
reserved quantity, bounded below by zero. Restock validation additionally rejects
negative inventory, reservations greater than physical quantity, and negative reorder
parameters. The only Phase 3 utility edit replaces its equivalent availability
calculation with the existing model property; pricing behavior is unchanged.

### Calculations and triggers

- Days remaining = available inventory / sales velocity, displayed to two decimals.
  Zero velocity returns JSON `null`, never infinity or a sentinel.
- Lead-time demand = sales velocity × configured lead-time days.
- Safety stock = ceil(sales velocity × safety-stock days), in whole units.
- Restock trigger requires positive demand and either available inventory <= reorder
  point OR available inventory < lead-time demand + safety stock.
- When triggered, target stock = lead-time demand + safety stock + existing
  `Inventory.reorder_quantity`. The existing data layer defines no supplier minimum
  or pack size; Phase 4 treats reorder quantity as an additional replenishment buffer.
- Recommended quantity = ceil(max(0, target stock - available inventory)), capped at
  `MAX_REORDER_QUANTITY`. Capping is explained and raises risk to high.

Calculations use Decimal arithmetic derived from shared velocity to avoid accumulating
floating-point error. Whole-unit rounding is conservative. Trigger/risk comparisons
use unrounded demand, independently of rounded display values.

No demand produces zero reorder even below the reorder point, null days remaining,
confidence 0.20, and low risk. Insufficient history or inactive products also produce
zero reorder and confidence 0.20; observed stockout risk is still reported so the
merchant can investigate. Healthy stock produces zero reorder.

### Configuration

Defaults in the existing Pydantic Settings system and `.env.example`:

```text
RESTOCK_LOOKBACK_DAYS=14
DEFAULT_LEAD_TIME_DAYS=5
SAFETY_STOCK_DAYS=2
MAX_REORDER_QUANTITY=500
```

Lookback and maximum quantity must be positive integers. Lead time and safety-stock
days must be finite and nonnegative. `RestockPolicy` permits validated per-instance
policy overrides for independent testing and future application use. Supplier lead
time is currently a global default, not supplier-specific data.

### Confidence and risk

Confidence is a deterministic availability/volume heuristic, **not a calibrated
probability**, and makes no volatility or demand-stability claim. For sufficient,
positive demand on an active product: 0.40 base + 0.15 for known inventory + 0.30
for >=15 recent orders, 0.20 for >=5, or 0.10 otherwise. Thus scores are 0.65–0.85.
Zero demand, insufficient history, or inactive status gives 0.20.

Risk classification:

- High: positive demand and available inventory <= lead-time demand, or quantity cap
  applied. Equality means stock is exhausted when replenishment arrives.
- Medium: reorder trigger reached without high-risk conditions.
- Low: no trigger and no projected stockout.

`stockout_risk` specifically describes the lead-time demand comparison; a capped
recommendation can be high risk without this boolean being true. Risk describes
inventory exposure even if insufficient history prevents a reorder proposal.

### Schema and API

`RestockRecommendation` validates finite metrics, nonnegative quantities, confidence
within [0,1], and the shared low/medium/high `RiskLevel` enum. It is frozen and contains
physical/available stock, velocity, days remaining, lead time, safety stock, lead-time
demand, reorder point, proposed quantity, reason, confidence, and risk. The original
Phase 4 field `estimated_daily_sales` is a computed alias of `sales_velocity`.

`POST /api/v1/restock/recommend`

Request:
```json
{"product_id": 12}
```
Example with physical stock 50, reserved 45, 56 recent units, 7 recent orders, reorder
quantity 40, and default policy:
```json
{
  "product_id": 12,
  "current_inventory": 50,
  "available_inventory": 5,
  "sales_velocity": 4.0,
  "estimated_daily_sales": 4.0,
  "estimated_days_remaining": 1.25,
  "recommended_quantity": 63,
  "reason": "Available inventory reached the reorder point or does not cover lead-time demand plus safety stock. Stock may be exhausted before or when replenishment arrives.",
  "confidence": 0.75,
  "risk_level": "high",
  "reorder_point": 10,
  "lead_time_days": 5.0,
  "safety_stock": 8,
  "projected_demand_during_lead_time": 20.0,
  "stockout_risk": true
}
```

Unknown product returns 404. Missing inventory or impossible inventory returns 422
with a meaningful message. Requests require a strict positive integer product ID.
No history returns a conservative structured recommendation rather than an error.

The API performs no writes. The separate application service
`services/restock/persistence.py:generate_and_persist_recommendation` optionally stages
an existing Recommendation row with type `restock` and status `pending`; it flushes
without committing. Caller owns commit/rollback. It never creates approvals, actions,
purchase orders, or inventory arrivals.

### Verification

```bash
cd backend
venv/bin/python -m pytest -q
venv/bin/python -m pytest tests/test_restock_agent.py tests/test_restock_rules.py tests/test_restock_api.py -q
venv/bin/python -m pytest tests/test_pricing_agent.py tests/test_pricing_rules.py tests/test_pricing_api.py -q
cd ../frontend
npm test -- --run
npm run build
```

Tests cover demand, reservations, zero sales, missing/invalid data, threshold boundaries,
capping, deterministic output, read-only generation, pending persistence, rollback,
and unchanged inventory/prices. Existing health and data-layer regressions remain in
the complete suite. Database integration tests use in-memory SQLite; live PostgreSQL
verification is separate. No standalone lint/type-check scripts are configured; the
frontend build runs TypeScript checks.

Phase 5 can consume independently callable Pricing and Restock Agents, structured
outputs, and optional pending persistence services. Orchestration and execution remain
future work.
