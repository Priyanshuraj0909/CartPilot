# PHASE 05 — MASTER ORCHESTRATOR

## Objective

Implement CartPilot's AI Manager.

## Workflow

SENSE
↓
BUILD CONTEXT
↓
DECIDE
↓
SELECT AGENTS
↓
RUN AGENTS
↓
COLLECT RESULTS
↓
DETECT CONFLICTS
↓
VALIDATE POLICIES
↓
CREATE ACTION PLAN
↓
REQUEST APPROVAL

## Example

Merchant Goal:

"Improve revenue while avoiding stockouts."

Orchestrator should:

1. Read inventory.
2. Read recent orders.
3. Calculate sales velocity.
4. Run Pricing Agent.
5. Run Restock Agent.
6. Compare recommendations.
7. Identify conflicts.
8. Produce unified recommendations.

## Conflict Example

Pricing Agent:

Increase price.

Restock Agent:

Inventory is critically low.

Orchestrator:

Flag the relationship and explain why the actions are related.

## Output

ActionPlan:

goal
summary
recommendations
agent_results
conflicts
risk
approval_required

## No Automatic Execution

Phase 5 is still recommendation-only.
---

## Implementation — Phase 5 complete

**The Master Orchestrator coordinates recommendations only. It does not execute
merchant actions.** No prices, inventory, orders, approvals, action records, or
recommendation records are written by orchestration.

### Supported goals and routing

| Goal | Selected agents |
| --- | --- |
| optimize pricing | pricing |
| increase revenue | pricing |
| avoid stockouts | restock |
| protect inventory | restock |
| increase revenue while avoiding stockouts | pricing + restock |
| improve revenue while maintaining inventory health | pricing + restock |

Case, surrounding whitespace, repeated spaces, and a trailing period are normalized.
“Improve revenue while avoiding stockouts” is an alias of the combined revenue/stockout
goal from the original phase specification. Other goals return 422 with enum choices;
there is no free-form or random routing.

### Request and merchant scope

`POST /api/v1/orchestrate`

```json
{
  "merchant_id": 1,
  "goal": "Increase revenue while avoiding stockouts",
  "product_ids": [1]
}
```

Product IDs are explicit and required: 1–100 unique positive integer IDs per request.
No merchant-wide or database-wide fallback exists. IDs are sorted for deterministic
processing. Merchant IDs and product IDs reject booleans, floats, and numeric strings.
Missing merchant/products return 404; products owned by another merchant return 403.
The whole scope is validated before analytics or specialist evaluation begins.

Optional `constraints` can tighten, but never exceed, configured global limits:

```json
{
  "max_price_increase_percent": 2,
  "max_price_decrease_percent": 5,
  "max_reorder_quantity": 100
}
```

Omitted limits inherit global settings. Unknown constraints, nonfinite percentages,
negative percentages, and nonpositive reorder caps are rejected. Existing minimum
cost markup remains enforced. No new dependencies or environment settings are needed.

This MVP validates merchant-product relationships; authenticated merchant identity
binding is not implemented by this phase.

### Sense and BusinessContext

`services/orchestration/context.py` builds a typed `BusinessContext` containing the
request, selected agents, sorted product snapshots, and one UTC `as_of` time. Existing
Phase 3 queries supply product details, current/cost prices, inventory/reservations,
reorder parameters, recent units/orders/revenue/velocity, lifetime order count, and
price-history count. No sales or inventory formulas are duplicated.

Identical pricing/restock lookback periods share the same signal object and queries.
Different configured lookbacks receive separate snapshots using the same `as_of`.
The snapshots are reused by all specialist calculations. Reads suppress autoflush so
analysis cannot implicitly write caller-owned pending changes. A supplied internal
`as_of` must have timezone information; the public API uses the current UTC time.

This is a shared time-bounded analysis context, not a database-wide repeatable-read
transaction. Concurrent external writes can still affect sequential database reads.

### Specialist execution and extension

`MasterOrchestrator` routes, constructs context, collects results, validates output,
and calls the coordinator. Agent calculations are sequential and do not run concurrent
queries against a shared AsyncSession.

The existing agents gained small `recommend(preloaded_signals)` methods; their
independent async `analyze` APIs delegate to the same calculators, with unchanged
rules. Restock has a reusable snapshot adapter with the existing inventory validation.
This avoids duplicate reads while preserving independently callable agents.

A typed callable registry maps `AgentName` to snapshot evaluators; tests can inject
controlled failures or proposals. Future agents require extending the name/schema,
routing table, adapter, and coordination rules, rather than changing sales analytics.
Only Pricing and Restock are currently implemented.

### AgentResult and partial failures

`AgentResult` wraps agent name, product ID, success, typed original recommendation,
risk, confidence, and structured error. Successful wrapper metadata must match the
recommendation. Output validation checks recommendation type, product identity,
snapshot prices/inventory, configured cost floor, and request limits.

Agent input errors, unexpected failures, and invalid outputs are isolated per
product/agent. Valid results survive. Failures set `complete=false`, overall risk to
high, overall confidence to zero, and retain `approval_required=true`. Errors use
stable codes and sanitized messages; exception details are not exposed in responses.
A request where all agents fail still returns an incomplete advisory plan with errors.
Context/database failures are request failures, rather than fabricated specialist data.

### Conflict and coordination rules

- A price decrease paired with **high restock risk** creates a high-severity
  `pricing_inventory_conflict`. This also catches capped replenishment proposals.
- Replenishment/verification takes precedence. The coordinated pricing action becomes
  `hold_price` at the current price, with `deferred=true`; the original discount remains
  visible in `agent_results` for auditability.
- A discount is also deferred when selected restock analysis fails, because inventory
  health cannot be verified. This creates no fabricated conflict.
- A price increase paired with high restock risk produces a `synergy` relationship,
  explains inventory sensitivity, and retains both recommendations. It is not a conflict.
- Comparisons only pair successful results for the same product. Independent products
  and pricing-only/restock-only goals never create artificial cross-agent conflicts.
- Insufficient history retains the existing agents' conservative results and low
  confidence. Orchestration does not make their proposals more aggressive.

Priority order is critical → high → medium → low, with product ID and agent name as
stable tie-breakers. Restock with projected stockout is critical; other high restock
risk is high; positive ordinary replenishment is medium; healthy monitoring is low.
Price changes are medium; unchanged or deferred prices are low. A zero-quantity restock
with elevated risk becomes `review_inventory`, not a purchase instruction.

Overall risk is the maximum agent risk, raised to high for conflicts or failures.
Overall confidence is the minimum agent confidence; conflicts multiply it by 0.8,
rounded to two decimals. It is a deterministic heuristic, not a calibrated probability.
Every plan requires human approval, including unchanged or incomplete plans. This is
an indicator only; no approval workflow or execution is implemented.

### ActionPlan and demos

`ActionPlan` contains merchant/goal, summary, selected agents and selection rationale,
ordered coordinated recommendations, original agent results, conflicts, compatible
relationships, overall risk/confidence, approval requirement, completion status, and
UTC creation time. The creation timestamp naturally changes between API calls;
selection, ordering, and decisions are reproducible for the same snapshot and policy.

A real endpoint response from an isolated in-memory database is saved in
[`docs/examples/orchestration-demo.json`](../docs/examples/orchestration-demo.json).
The demo uses Wireless Mouse, price 999, available stock 8, velocity 5/day, and a
reorder buffer of 40. Results: restock 67 units first (critical), review price 1048.95
second (medium), high overall risk, approval required, and a compatible relationship.
No action is executed.

Pricing-only and restock-only routing are verified by integration tests. A controlled
injected discount demo verifies conflict deferral; current low-stock pricing rules
normally propose a hold or increase, so tests explicitly supply the conflicting
specialist proposal rather than changing established pricing behavior.

### Persistence and safety

Orchestration does not call either agent's optional persistence service. Plans are
returned to the caller, avoiding duplicate or misleading Recommendation records.
Existing independent services still support explicit pending proposal persistence.
No new database schema/migration is required. Plan persistence and approvals can be
introduced in a later phase with explicit application logic.

### Verification

```bash
cd backend
venv/bin/python -m pytest -q
venv/bin/python -m pytest tests/test_orchestrator.py tests/test_orchestration_rules.py tests/test_orchestration_api.py -q
cd ../frontend
npm test -- --run
npm run build
```

The complete backend suite includes health, data-layer, pricing, restock, and new
orchestration regressions. Tests cover routing, multi-product scope, deterministic
snapshots/order, conflicts/synergies, partial/all failures, sanitized errors, constraints,
merchant isolation, and unchanged database records. Database integration uses SQLite;
live PostgreSQL verification was not performed. The frontend build includes TypeScript
checks; no separate lint or type-check commands are configured.

Phase 6 may consume the typed advisory API for the merchant dashboard. Promotion,
Listing, LLM workflows, execution, and external integrations remain future work.
