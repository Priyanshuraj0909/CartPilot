# Verified algorithms and formulas

These are deterministic business rules, not trained forecasting models. Source of
truth: `backend/app/services/{pricing,restock,promotion,listing,orchestration,policies}`.
Confidence, risk and priority are separate heuristic outputs; none predicts revenue lift.

## Shared signals

Sales velocity `v = eligible units sold / configured lookback days` (default 14).
Orders are merchant/product scoped, within the observation window, excluding cancelled
orders. A short observed history is not silently substituted as the denominator.
Available stock `A = max(0, physical − reserved − unavailable)`; unavailable stock is
important for imported Shopify inventory. Missing inventory is unknown, not evidence
of a safe stock level. Coverage `A/v`; zero velocity yields no finite stockout estimate.

Strong sales: v ≥ 1 unit/day **or** lookback units ≥ 10. Weak sales: sufficient data and
(v < .25 **or** units ≤ 2). Low stock: A ≤ reorder point. High inventory: A exceeds
`reorder_point + 1.5 × reorder_quantity` **or** coverage exceeds 45 days. These overlap
in some cases; agent decision ordering and orchestrator safety resolve competing signals.

## Pricing Agent

Decision order: unknown inventory or insufficient history → hold; low stock with strong
sales → bounded increase; low stock otherwise → hold; healthy stock with strong sales
→ increase; high stock with weak sales → decrease; otherwise hold. Default movement
is 5%, capped by default 10% increase/decrease.

`delta% = (recommended − current) / current × 100`.
Upper cap is current × (1 + maximum_increase/100), rounded down to cents; lower cap
rounds current × (1 − maximum_decrease/100) up to cents. Cost floor is
`cost × (1 + MIN_MARGIN_PERCENT/100)`, rounded up. **This setting is markup over cost,
not retained gross margin.** Conflicting cost floor and movement limits raise a safe
failure instead of silently selecting an unsafe price. Unknown cost blocks pricing.

Confidence: .20 if insufficient data; otherwise .35 + order-volume contribution
(.25 for ≥15 recent orders, .15 for ≥5) + .15 if physical inventory >0 + .10 if price
history exists + .15 if v≥.5, bounded to [.10,1]. Risk is high for insufficient data,
cost clamp, low stock or gross margin <5%; otherwise medium for capped movement or
absolute delta≥5%; otherwise low. A high-risk pricing proposal can remain a medium
**priority** review: urgency and execution risk are different concepts.

Example, actual four-product fixture: Mouse 999.00 → 1048.95 (+5%), high risk because
stock is constrained. This is a recommendation; the product changes only after approval
and separately confirmed execution.

## Restock Agent

Lead-time demand `D = v × lead_time_days` (default 5).
Safety stock `S = ceil(v × safety_stock_days)` (default 2).
Trigger when v>0 and `(A ≤ reorder_point or A < D+S)`.
Reorder quantity `Q = min(max_quantity, max(0, ceil(D+S+reorder_quantity−A)))`.
The stored reorder_quantity is an additional buffer, **not a supplier minimum**.
Stockout risk when v>0 and `A ≤ D`; equality is risky because stock is exhausted on arrival.
Days remaining is A/v, rounded to 2 decimals, or null at zero velocity.
Inactive/insufficient-history/zero-demand products do not receive a positive reorder.
A capped order can leave residual exposure. No purchase order is sent or stock added.

Confidence: .20 for insufficient/zero-demand/inactive cases; otherwise .40 + .15 for
known inventory + .30/.20/.10 for ≥15/≥5/fewer recent orders. Risk high for stockout
or capped quantity, medium for a noncritical trigger, otherwise low.
Actual Mouse fixture recommends **67 units** under default policy.

## Promotion Agent

Compare velocities in newer and older halves of the lookback window.
Trend change `(recent_velocity − previous_velocity)/previous_velocity × 100`;
previous=0 means increasing if recent>0, stable otherwise. Default decline threshold
is strictly below −20%. Incomplete history is explicitly insufficient.
High inventory: coverage>45 days, or zero-sales stock≥30. Weak movement: v<1.5
or declining trend. Low stock/reorder point and fresh stockout assessment block promotions.

Desired discount: 15% at zero sales, 10% for decline, otherwise 5% (configurable).
Retained gross margin `GM% = (selling − cost)/selling × 100`.
Minimum safe price `F = cost / (1 − minimum_margin/100)`.
Maximum margin-safe discount `max(0,(1−F/current_price)×100)`.
Final discount is min(desired, configured maximum, margin-safe maximum), rounded down
at .01%; candidate price is rounded to cents and rechecked against F. Unsafe/no-op
candidates return no promotion. Unknown cost blocks margin-dependent analysis.
Example: fixture Speaker 1499.00 → 1349.10 (10%); orchestrator defers the competing
base-price decrease. Launching a campaign remains simulated, not an external action.

## Listing Agent

Clean HTML, ignore script/style text, inspect title/description lengths and duplication,
category alignment and mentioned category-specific attributes. Mention does not prove
an attribute is true or applicable. Unknown categories require manual review.
Quality = `.25×title_pass_fraction + .35×description_pass_fraction +
.25×attribute_fraction + .15×category_alignment`, rounded to 2 decimals.
Title has 3 checks, description 4; unknown attribute categories use .5. Alignment
is 1 for consistent, .5 for unverified, 0 otherwise. Default poor-quality threshold .6.
Confidence .20 for sparse sources; otherwise min(.90,.45 + .20 if description + .15
if category + .10 if SKU). Risk high for sparse/inconsistent sources, medium for
substantial changes or poor quality, otherwise low.
Suggestions copy existing facts/identifiers, preserve negations, and request verification
for missing information. No unsupported battery, material, connectivity or performance
claim is invented. Keywords are extracted tokens, not measured SEO ranking predictions.

## Master Orchestrator and cross-agent intelligence

Fresh merchant context → goal-based specialist selection → structured result collection
→ safety overrides → conflicts/synergies/dependencies → sorted bounded advisory queue.
Balanced Growth requests all four agents. Inventory exposure can override other goals.

Weights for Balanced Growth: inventory .30, revenue .30, margin .20, catalog .20.
`score = agent_goal_weight × clamp(signal_strength,0,1) × confidence`, rounded to 4 decimals.
Agent weight: restock inventory; pricing revenue+margin; promotion revenue; listing
catalog plus .5×revenue for strong listing issues. Critical inventory overrides scoring;
otherwise high at score≥.15 or severe listing issue, medium≥.05, low below .05.
Balanced Growth price-change reviews are medium. Sorting: priority, descending score,
product ID, agent name. Default action queue budget 5; omitted and blocked work remain visible.

Conflicts: base-price change vs temporary discount; demand stimulation vs constrained
inventory. Synergy: bounded price increase + replenishment; factual listing improvement
supports promotion review. Dependency: poor listing should be reviewed before discount
or price-reduction remedies. Simulated restock does not satisfy actual replenishment.
Partial specialist failures remain visible; the plan is marked incomplete. No agent
can approve or execute an action through orchestration.

## Guarded action techniques

Typed immutable payload + merchant scope + finite-state lifecycle + unique workflow
identity + atomic execution claim + fresh source/policy validation + transaction/savepoint
rollback + persistent audit. Pending → validated → awaiting approval → approved →
executing → executed/failed. Rejected/failed paths do not authorize execution.
Stale execution may retain approved state with a blocked outcome; check result/policy,
not only status. Repeated completed execution returns the prior result without another
price-history entry. SQLite tests do not prove PostgreSQL concurrent locking behavior.
