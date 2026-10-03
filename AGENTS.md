# CARTPILOT AGENT RULES

## Before Coding

Always inspect:

MASTER_ORCHESTRATOR.md
PLAN.md
ARCHITECTURE.md
current phase document

---

## Coding Style

Backend:

Python 3.12+

Use:

- type hints
- Pydantic
- async where appropriate
- clear module boundaries
- small functions

Frontend:

TypeScript

Avoid:

- any unless necessary
- duplicated components
- business logic in UI

---

## AI Development

Never allow an LLM to directly:

- modify database records
- change prices
- create promotions
- place purchase orders

Use structured outputs and application-level validation.

---

## Testing

Every feature requires tests.

Minimum:

- happy path
- invalid input
- boundary conditions
- failure case

---

## Git

Use small commits.

Format:

feat:
fix:
test:
docs:
refactor:
chore:

---

## Dependency Rule

Before adding a dependency:

1. Check whether an existing dependency already solves the problem.
2. Prefer established libraries.
3. Avoid unnecessary packages.

---

## Secrets

Never hardcode:

API keys
tokens
passwords
credentials

Use .env.

Never commit .env.

---

## Completion

Never say "done" until:

- implementation exists
- tests pass
- build passes
- documentation is updated

## Final verified agent guide (Phase 14)

The rules above remain repository instructions. The following describes implemented
product agents, not instructions to spawn coding assistants. All algorithms are
deterministic; see [formulas](docs/ALGORITHMS.md) for exact thresholds/rounding.

### Pricing Agent

- Purpose: explain bounded price-review opportunities.
- Inputs: product/current price/cost, scoped orders, inventory and price history.
- Signals: sales velocity, sufficient history, stock coverage and cost.
- Algorithm: ordered hold/increase/decrease rules; caps and cost/markup floor.
- Output: typed current/proposed price, reason, heuristic confidence/risk and delta.
- Guardrails: positive finite prices, known cost, stock/history checks, bounded movement.
- Limitations: no price-prediction ML or elasticity estimate; recommendation alone changes nothing.

### Restock Agent

- Purpose: estimate replenishment need and stockout exposure.
- Inputs: physical/reserved/unavailable stock, orders, reorder point/buffer and configured lead/safety days.
- Signals: available stock, demand velocity, lead-time demand and coverage.
- Algorithm: ceiling-rounded demand/safety/buffer deficit, trigger and maximum cap.
- Output: quantity, coverage, stockout flag, reason, confidence and risk.
- Guardrails: verified demand/inventory, active product, nonnegative/capped quantity.
- Limitations: fixed planning assumptions; executor records simulation, no supplier order/stock arrival.

### Promotion Agent

- Purpose: propose margin-safe discounts for excess/slow inventory.
- Inputs: price/cost, available stock, sales half-windows, product history and restock assessment.
- Signals: excess coverage, weak/declining sales, current stockout risk and retained margin.
- Algorithm: mild/moderate/severe discount bounded by cap and cost/(1−margin) floor.
- Output: candidate flag/discount/price/trend/reason/confidence/risk.
- Guardrails: stockout/reorder protection, known cost, complete history and cent-rounded margin recheck.
- Limitations: no promotion-optimization ML; campaign execution is simulated, no live launch.

### Listing Agent

- Purpose: identify factual title/description/completeness issues.
- Inputs: title, description, category and SKU; no verified structured-attribute database.
- Signals: text lengths/duplication, category terms and mentioned attributes.
- Algorithm: weighted check score, grounded copy/identifier suggestions and verification requests.
- Output: current/proposed content, issues, attributes, keywords, quality/confidence/risk.
- Guardrails: preserve facts/negations, bounded output, no invented product features.
- Limitations: heuristic catalog checks, not SEO/conversion prediction; missing attributes need merchant verification.

### Master Orchestrator

- Purpose: create one explainable merchant-goal advisory plan.
- Inputs: merchant scope/goal, bounded product selection and shared fresh signals.
- Signals: stock exposure, revenue/margin opportunities, excess stock and listing quality.
- Algorithm: goal/opportunity selection, structured specialist collection, inventory override,
  conflict/synergy/dependency rules, goal-weighted scoring and bounded sorted queue.
- Output: recommendations, selected/blocked/omitted actions, relationships, risk/confidence and failures.
- Guardrails: scope checks, inventory safety, incomplete-result visibility; no implicit approval/execution.
- Limitations: heuristic goal weights, max 100 analyzed products, no autonomous learning or external agent network.
