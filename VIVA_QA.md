# CartPilot viva preparation

## One-page quick reference

**Goal:** coordinate pricing, stock, promotions and listing decisions above merchant data.
**Architecture:** Shopify/demo → SQLAlchemy data/signals → four rule-based agents →
Master Orchestrator → conflicts/synergies/dependencies → advisory queue → policies →
human approval → separate confirmed local/simulated executor → audit.
**Four agents:** Pricing, Restock, Promotion, Listing. Orchestrator is the coordinator.
**Formulas:** velocity=lookback units/days; available=max(0,physical−reserved−unavailable);
coverage=available/velocity; demand=velocity×lead time; safety=ceil(velocity×safety days);
reorder=min(cap,max(0,ceil(demand+safety+buffer−available)));
gross margin=(price−cost)/price×100; priority=goal weight×strength×confidence, subject to
inventory overrides. Pricing minimum margin is markup over cost, not promotion gross margin.
**Guardrails:** typed immutable payload → scope/policy → approval → confirm → fresh
revalidation/atomic claim → execution → audit. Approved is not executed.
**Stack:** Python/FastAPI/Pydantic/async SQLAlchemy/Alembic/PostgreSQL; React/TypeScript/
Vite/Tailwind; pytest/Vitest; optional Redis diagnostics; read-only Shopify GraphQL.
**Demo:** Mouse critical restock 67 → Headphones listing → Speaker 10% promotion → Mouse
5% price review. Safe Mouse local edit 999→1048.95; 50% change blocked by 10% policy.
**Honesty:** deterministic expert-style rules, no LLM/ML/RL, no measured revenue uplift.
Restock/promotion execution is simulated; Shopify is read-only. No production auth;
trusted demo only. Future forecasting/auth/supplier adapters are proposals, not features.
**Evidence:** 560 backend / 76 frontend tests, build, migration/seed and browser checks.

## Project basics

### 1. What problem does CartPilot solve?
Pricing, inventory, discounts and catalog decisions can conflict when managed separately.
CartPilot makes their signals/recommendations visible in one explainable priority plan.

### 2. What is the project in one sentence?
A deterministic multi-agent e-commerce decision-support MVP with goal-based coordination,
human approval, safe local/simulated execution and auditable outcomes.

### 3. Why an agentic architecture?
Each specialist owns a bounded decision domain and a typed output; coordination can
resolve inter-domain conflicts without mixing all rules into one opaque decision block.

### 4. Why not one monolithic AI model?
This MVP favors testable, explainable rules and separate guardrails. It does not call an
AI model at all, so this is an architectural choice, not a measured model comparison.

### 5. Which specialists exist?
Pricing Agent, Restock Agent, Promotion Agent and Listing Agent. The Master Orchestrator
builds/coordinates the unified plan rather than acting as another specialist.

### 6. What does the Master Orchestrator do?
Builds scoped context, selects specialists by goals/opportunities, collects partial results,
resolves conflicts/dependencies, calculates priority and produces an advisory queue.

## Algorithms

### 7. How is sales velocity calculated?
Eligible units sold in the configured window divided by its days; default 14 days.
Cancelled orders and out-of-window data are excluded. See docs/ALGORITHMS.md.

### 8. Why distinguish available and physical inventory?
Reserved and unavailable stock cannot be immediately sold: available is
max(0,physical−reserved−unavailable). Unknown inventory must be verified.

### 9. How do you estimate stockout?
Available/velocity gives coverage. Stockout risk exists when available≤velocity×lead time.
Zero velocity produces no finite stockout estimate; it is not a predicted calendar event.

### 10. How is reorder quantity calculated?
When triggered, ceil(lead-time demand + ceiling-rounded safety stock + configured buffer
− available), floored at zero and capped. Buffer is not a supplier minimum.

### 11. Is supplier lead time measured automatically?
No. It is a configured planning assumption, default five days. Safety days default two.
No supplier API or real purchase-order execution exists.

### 12. When does pricing change?
Strong demand with low/healthy stock can produce a default 5% increase; weak demand
with excess stock can produce a decrease. Missing/insufficient data holds the price.

### 13. How do you protect cost and movement limits?
Cap movement by configured increase/decrease limits and enforce the cost/markup floor.
If they conflict, fail safely. Monetary boundaries use directional cent rounding.

### 14. How is margin calculated?
Gross margin=(selling−cost)/selling×100. Pricing MIN_MARGIN_PERCENT is markup over cost;
promotion retained-margin floor instead uses cost/(1−required_margin/100).

### 15. How do promotion guardrails work?
Require excess stock and weak/declining sales, avoid stockout/low inventory, limit discount
and preserve retained gross margin. Rounded candidate price is rechecked.

### 16. How is sales trend calculated?
Compare newer/older half-window velocities. With a nonzero previous velocity use
percentage change; previous zero has explicit increasing/stable handling.

### 17. How is listing quality measured?
Weighted pass fractions: title .25, description .35, mentioned attributes .25, category
alignment .15. It is a text heuristic, not marketplace SEO ranking or conversion prediction.

### 18. How do listing suggestions avoid hallucinations?
They reuse existing facts/identifiers, preserve qualifiers/negations, and ask the merchant
to verify missing details. A mention is not independent verification of an attribute.

### 19. What does confidence mean?
A bounded heuristic of data availability, observation volume and text completeness,
depending on the agent. It is not calibrated probability or model accuracy.

### 20. How do priority and risk differ?
Priority orders business urgency; risk describes uncertainty/safety exposure. A Mouse
price increase is high risk due to low stock but medium-priority review under Balanced Growth.

### 21. How are conflicts detected?
Structured rule comparisons detect overlapping price/discount changes and demand stimulation
against constrained stock. The competing proposal is blocked/deferred with an explanation.

### 22. What are synergy and dependency examples?
A bounded price increase can coexist with restock planning (synergy). Poor listing quality
can require factual review before promotion or price reduction (dependency).

### 23. How is priority calculated?
Goal weight×bounded signal strength×confidence; hard inventory safety overrides it.
Sort by priority, score, product ID and agent. Omitted/blocked work remains visible.

## Architecture and data

### 24. Why FastAPI?
It supports typed API contracts, async handlers and generated OpenAPI documentation,
matching this Python async service design. We do not claim it is universally faster.

### 25. Why PostgreSQL?
Relational identities/constraints/transactions fit merchant data and guarded workflows;
it is the deployment target. SQLite provides isolated tests, not identical concurrency.

### 26. Why React and TypeScript?
Reusable UI components display structured recommendations/actions; TypeScript checks
frontend contracts, and Vite builds the static frontend artifact.

### 27. How do agents communicate?
The coordinator invokes existing Python specialist interfaces against shared scoped
context/session snapshots; results follow Pydantic contracts, not an external agent network.

### 28. What is Sense → Decide → Act → Learn here?
Sense collects store signals; Decide applies specialists/coordination; Act uses guarded
human-approved local/simulated execution. Learn currently means recording outcomes for
review, not automatic model updates or reinforcement learning.

### 29. What are the major database models?
Merchant, Product, Inventory, Order, OrderItem, PriceHistory, AgentRun, Recommendation,
Action, Approval, AuditLog, ShopifyConnection and external product/order mappings.

### 30. Why Alembic?
Versioned schema migrations make empty-database setup and controlled upgrades reproducible.
They run as a separate release command rather than every request/worker startup.

### 31. How are integrity and scope maintained?
Foreign keys, constraints, unique identities and scoped queries. Ownership checks exist,
but without authentication they do not establish the caller's merchant identity.

### 32. Is Agent Activity persistent?
The AgentRun model exists, but the current Agent Activity UI reflects browser-session
analysis history. Persisted guarded actions/audit are separate.

## Safety and workflow

### 33. Can an agent directly change price?
No. Analysis proposes data only. A separate executor changes local price/listing data
after policy, human approval, confirmation and current-state checks.

### 34. Why human approval?
Heuristics and incomplete data can produce risky proposals. Human review is an explicit
boundary, and approval cannot bypass execution-time validation.

### 35. What is policy revalidation?
Compare immutable proposal/source values with fresh price, cost, inventory or listing
facts and rerun applicable bounds immediately before execution.

### 36. What if inventory changes after approval?
An approved promotion may be blocked at execution due to newly critical stock. The
existing automated test proves this using an isolated fixture; no campaign is launched.

### 37. How do you prevent duplicate execution?
Unique workflow identity deduplicates creation; atomic claims/state rules guard execution.
Already-executed actions return the recorded result without another price-history change.

### 38. What happens on failure?
Transactions/savepoints roll back mutation paths; workflow/audit records explain failure.
Sanitized API responses do not expose infrastructure details or credentials.

### 39. What does the audit store?
Action lifecycle/review/execution events and safe result metadata, including before/after
local price changes. It does not store Shopify credentials or a claimed ML training loop.

### 40. Is production authentication implemented?
No. Production gates local write/Shopify routes; read access still needs a protected
hosting/network boundary. CORS is not authentication or multi-tenant authorization.

## Shopify and AI claims

### 41. How does Shopify integration work?
A closed Admin GraphQL query registry imports products/variants, location inventory and
recent orders into mapped local records through bounded manual read-only sync.

### 42. Why read-only?
External merchant writes require stronger authorization, reconciliation and failure controls.
The current scope supports decision analysis without risking remote store changes.

### 43. How are duplicate sync and variants handled?
External IDs map variants to local products and orders to local orders; merchant/store
binding and unique identities make repeated sync idempotent. SKU alone is insufficient.

### 44. What happens if Shopify is unavailable?
The integration reports a bounded failure; local/demo data and agents remain usable.
Faculty demo uses synthetic mocked HTTP, explicitly disclosed.

### 45. Is CartPilot machine learning? Where is AI used?
No trained model or LLM is implemented. It is an expert-style deterministic decision
and coordination system. “AI Manager” is product positioning, not a claim of ML inference.

### 46. Does the system learn automatically or act autonomously?
No. Audit/history support review. There is no model retraining, RL, autonomous approval
or external business execution.

## Testing, limitations and future scope

### 47. How were agents and guardrails tested?
Happy paths, invalid inputs, edge bounds, unknown/missing data, scoping, partial failures,
state transitions, stale sources, rollback and duplicate execution in pytest/Vitest.

### 48. How did you test Shopify without real credentials?
Synthetic HTTP fixtures cover read-only queries, variants, locations, pagination/retries,
unknown data and repeated synchronization. Browser sync is mocked, not live-store evidence.

### 49. What is regression testing and the final result?
Rerunning earlier tests catches behavior broken by later changes. Final run: 560 backend
and 76 frontend tests pass; TypeScript/Vite production build passes. Lint is not configured.

### 50. What are the key limitations and next steps?
No advanced forecasting, production auth, external supplier/campaign execution, Shopify
writes or learning loop. Future work would add validated forecasting/auth/integrations
with explicit safety design, not silently change existing behavior.

### 51. How would it scale?
Bounded product/action queues and shared snapshots help this MVP. Optimize remaining
per-product sales queries, control connection budgets, add measured load/concurrency
checks and production identity/rate controls before broad multi-store use.

### 52. What is technically interesting or novel?
The combination of specialized explainable rules, goal-based coordination, visible
conflicts and a separate audited human gate. This is an engineering contribution;
we do not claim scientific novelty, superior benchmark accuracy or measured business lift.
