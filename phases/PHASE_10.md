# PHASE 10 — CROSS-AGENT INTELLIGENCE

Status: COMPLETE. Goal-driven planning coordinates the existing Pricing, Restock,
Promotion and Listing specialists. No new specialist or production integration exists.
Agents recommend, the orchestrator coordinates, policy validation protects, humans
approve, the Phase 9 executor acts, and audit logs record the result.

## Goals and compatibility

Six controlled goal identifiers:

| Goal | Strategy |
| --- | --- |
| maximize_revenue | Bounded pricing opportunities, controlled promotion assessment and listing improvements; inventory safety first |
| avoid_stockouts | Restock/stock verification dominates; suppress demand stimulation on constrained stock |
| reduce_excess_inventory | Promotion, pricing assessment and listing improvement for appropriate excess/slow movers |
| improve_product_performance | Combine relevant price, promotion and listing opportunities with inventory overrides |
| improve_catalog_quality | Listing specialist where text has issues; critical inventory remains visible |
| balanced_growth | Explicit broad assessment by all four specialists, balancing inventory, revenue, margin and catalog quality |

Earlier space-separated goals retain their routing and explicit-product requirements.
The six new goals use context-aware selection and enhanced plan output. Labels in AI
Manager are human-readable, with Balanced Growth selected initially.

## Fresh context and opportunity detection

The shared context reuses Pricing sales/inventory snapshots by lookback window,
Promotion trend/age enrichment, Restock calculations and Listing quality checks.
All ownership is preflighted before specialist calls. Analysis uses one as_of time,
non-cancelled merchant-scoped order windows, and current source product fields.

Before invoking specialists, detect per product:

- Pricing: sufficient data with strong demand and low/healthy inventory, or weak
  demand and surplus inventory. Excess stock also warrants pricing assessment,
  even when the specialist ultimately holds price.
- Inventory risk: missing/invalid inventory, high replenishment risk or stockout
  exposure from the existing lead-time rules. Positive reorder needs also select Restock.
- Excess/slow mover: active product, known high inventory and sales velocity below
  SLOW_SALES_THRESHOLD. Promotion further checks observation age, trend and margin.
- Listing: existing quality-check issues and quality score. Minor issues without a
  safe content change do not consume the action queue; poor content can require
  merchant verification even if missing facts cannot be generated safely.

New goals select specialists independently for each product. Catalog goals do not run
pricing/promotion unnecessarily; stockout prevention mainly selects Restock. A neutral
healthy product need not invoke any specialist for a focused revenue goal. Balanced
Growth explicitly permits broad analysis. Gathering signals is distinct from invoking
all four specialist agents. Selection reasons are returned per product and specialist.

Plans never use saved recommendations as operational truth: fresh specialist analysis
replaces stale proposals. Planning stages no database records, so repeated analysis
cannot flood Recommendations/Actions/Approvals tables. Equivalent current-session
results replace prior copies in the UI; Phase 9 creation deduplication remains intact.

## Relationships and safety

RecommendationRelationship records product, agent pair, type, severity, explanation
and recommended_resolution. Types are conflict, synergy, dependency and independent.

| Pair | Behavior |
| --- | --- |
| Pricing / Restock | Block price reductions on constrained/unverified stock; explain compatible bounded increases |
| Promotion / Restock | Block demand stimulation; depend on physically healthy, verified inventory |
| Pricing / Promotion | Never stack concurrent base-price and temporary-discount changes; goal strategy chooses one |
| Listing / Promotion | Explain synergy on poor listings and defer promotion until factual listing review and fresh analysis |
| Pricing / Listing | Defer reductions on poor listings; verify content and reassess demand first |
| Restock / Listing | Independent tasks; no fabricated conflict |

Excess Reduction and Product Performance prefer promotion over overlapping price
changes. Balanced Growth prefers a temporary promotion for excess stock when the
alternative is a base-price reduction; otherwise Pricing takes precedence. Maximize
Revenue prefers the bounded pricing proposal. Inventory safety overrides every goal
and every weight, including when inventory analysis fails. Failed inventory analysis
produces a critical verification item rather than disappearing from the plan.

Blocked proposals remain visible with reasons and depends_on IDs (`product:agent`).
When a specialist correctly returns no promotion for constrained stock, a synthetic
blocked decision explains that safety suppression; it has no approval candidate or
invented discount. Dependency items stay blocked until resolution and fresh analysis.
A simulated restock does not establish stock arrival or satisfy a stock dependency.
Explicitly selected inactive products cannot become operational approval candidates;
store-wide mode analyzes active products only.

Phase 9's price policy also revalidates inventory on price reductions. Direct action
creation cannot bypass inventory protection by extracting a raw discounted proposal.
All other Phase 9 policies, source checks, approvals, execution confirmation, rollback
and audits remain in force. Planning never calls the executor or grants approval.

## Deterministic priority and confidence

Weights are centralized in services/orchestration/strategy.py:

| Goal | Inventory | Revenue | Margin | Catalog |
| --- | ---: | ---: | ---: | ---: |
| balanced_growth | .30 | .30 | .20 | .20 |
| maximize_revenue | .20 | .45 | .20 | .15 |
| avoid_stockouts | .60 | .15 | .15 | .10 |
| reduce_excess_inventory | .20 | .45 | .10 | .25 |
| improve_product_performance | .20 | .30 | .15 | .35 |
| improve_catalog_quality | .10 | .10 | .10 | .70 |

Score = relevant goal weight × signal strength × specialist confidence, rounded to
four places. Restock uses inventory weight; Pricing uses revenue + margin; Promotion
uses revenue. Listing uses catalog weight, plus half the revenue weight for poor
quality (a heuristic relevance adjustment, not predicted conversion lift).

Strength: urgent inventory 1, other replenishment .6; price changes min(1, absolute
percentage change / 5); controlled promotion 1; poor listing quality 1, smaller safe
content changes .5. Priority is critical for inventory exposure/verification; otherwise
high at score >= .15 (or poor listing quality), medium at >= .05, low below .05.
Balanced Growth keeps ordinary bounded price changes medium priority. Safety decisions
are applied before queue selection; weights cannot make blocked actions executable.

Sort by priority, descending score, product ID, then agent name. Same goal, snapshot,
configuration and source data produce the same selection, relationships and ordering.

Overall risk preserves the strongest specialist/action risk; failures, unresolved
inventory exposure or truncated store scope force high risk. Confidence is the minimum
specialist confidence, reduced 20% for conflicts and another 20% for truncated scope.
A failed specialist yields zero confidence and an incomplete plan, with successful
results preserved. These are deterministic decision heuristics, not accuracy or sales
uplift probabilities. No LLM is required or used in Phase 10.

## API and budgets

`POST /api/v1/orchestrate`

Real isolated four-product request:

```json
{"merchant_id":1,"goal":"balanced_growth","product_ids":[1,2,4,5]}
```

New goals also accept omitted/null product_ids for store-wide mode. `limit` defaults
to 100 and accepts strict integers 1–100. The scope uses active merchant products,
ordered by product ID, and reads limit + 1 IDs to report scope_has_more. Truncated
scope is explicitly incomplete; the user can select further products for another
analysis. Empty active scope returns a valid empty plan. Explicit scopes require
unique strict positive IDs and have a maximum of 100. Missing/foreign scope returns
404/403, invalid inputs 422 and handled storage failures sanitized 503.

Existing optional constraints tighten global price-change, discount and reorder limits.
MAX_ACTIONS_PER_PLAN (default 5, configurable 1–100 in Settings/.env.example) bounds
the main priority queue. Every omitted item is retained in omitted_actions, and a
warning counts critical overflow. Blocked items have a separate queue. Critical items
are never silently discarded. API size is also bounded by the 100-product scope.

Enhanced ActionPlan retains original agent_results and legacy fields and adds:

- products_analyzed, opportunities and opportunity_summary product references
- recommendation_relationships with all four relationship types
- prioritized_actions, blocked_actions, omitted_actions
- warnings and scope_has_more

PrioritizedAction includes stable ID, rank, product/name, agent, action_type, priority,
score, rationale, confidence/risk, blocked/reason, depends_on and approval_candidate.
No-op holds do not become operational candidates. Critical verification can remain
visible without an executable mutation. Legacy plan fields remain available.

## Frontend and Phase 9 integration

AI Manager provides six goal cards, the controlled selector, selected-product analysis
and Analyze Store. The enhanced view shows CartPilot Store Summary, opportunity counts,
priority actions with proposed values, blocked actions, conflicts/synergies/dependencies,
selection reasons, partial failures, critical overflow and original specialist proposals.
Recommendations renders the same enhanced plan for current-session results.

Only an eligible, unblocked item in the main queue exposes Create Action for Review.
It submits the original typed specialist output to Phase 9. Policy validation and
human approval/rejection remain separate from explicit execution confirmation.
Additional queue items require prioritization/reanalysis; blocked or verification-only
items cannot create an action from the plan view. No automatic execution occurs.

## Four-product flagship demo

Reproduce against a fresh, isolated in-memory SQLite store:

```bash
cd backend
venv/bin/python -m tests.demo_cross_agent
```

The script submits a real ASGI HTTP request, checks unchanged source data and zero
created Actions/Approvals/Recommendations, and emits the full response. It does not
connect to the developer's database. Results are saved in
[docs/examples/cross-agent-demo.json](../docs/examples/cross-agent-demo.json).

| Product | Conditions | Balanced Growth result |
| --- | --- | --- |
| Wireless Mouse | Strong demand, 8 available units | Critical restock of 67 units; medium bounded price increase 999 → 1048.95; promotion blocked |
| Bluetooth Speaker | 120 units, declining sales, margin room | High priority controlled 10% promotion, 1499 → 1349.10; base pricing holds |
| Headphones | Missing description, weak sales, normal physical stock | High priority grounded listing review; reductions/promotion deferred for listing dependency |
| Keyboard | Healthy stock/neutral demand, good factual listing | No urgent action |

Actual ordered queue: Mouse Restock → Headphones Listing → Speaker Promotion → Mouse
Pricing. Overall risk high; confidence .32. The summary reports four analyzed products,
one inventory risk, two excess/slow movers, two pricing opportunities and two listing
issues (one Mouse issue is minor and requires no generated content change).

## Verification

29 Phase 10 backend tests; 362 total backend tests. Nine new frontend tests; 57 total
frontend tests. TypeScript/Vite production build passes. No lint script is configured.
No dependency or migration was added for Phase 10.

```bash
cd backend
venv/bin/pytest -q tests/test_cross_agent.py
venv/bin/pytest -q
cd ../frontend
npm test -- --run
npm run build
```

Tests cover all goals, four-product coordination, deterministic fresh snapshots,
context-aware selection, goal-dependent conflict resolution, inventory/listing
relationships, direct-action safety, partial failures, unknown/inactive products,
merchant isolation, stale saved proposals, store-wide bounds/empty scope, twenty
opportunities with a five-action budget, critical overflow, no writes, session dedup
and plan → Phase 9 → explicit guarded execution. Frontend tests cover goals/store
analysis, summary/queue, all relevant relationships, blocked controls, overflow,
failures and action creation without approval or execution.

## Limitations and stop

Signals and scores remain rule-based; they do not estimate causality, elasticity or
conversion uplift. Plans are advisory response/session artifacts, not durable DAGs.
Dependencies require merchant verification and fresh analysis, not automatic execution
of a chained workflow. Minor listing issues may need facts the generator cannot supply.
Store-wide scope is bounded rather than a full-store database snapshot; separate
read queries can observe concurrent store changes, so Phase 9 revalidation is essential.
Legacy goal aliases preserve earlier behavior; new goal identifiers enable intelligence.
Development identity and local/simulated execution limitations from Phase 9 remain.

Future production work needs authenticated identity, read-only commerce connectors,
currency/supplier-specific data, deployed PostgreSQL validation and explicit guarded
write integration. None is implemented here. Stop after Phase 10.
