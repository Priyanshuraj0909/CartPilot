# CARTPILOT MASTER ORCHESTRATOR

## 1. Project Identity

Project Name:
CartPilot

Project Description:
CartPilot is an AI manager for e-commerce that sits above inventory and
storefront data and coordinates specialized agents for pricing, restocking,
promotions, and product listings.

Core Operating Loop:

SENSE → DECIDE → ACT → LEARN

---

## 2. Primary Goal

Build a working MVP of CartPilot that can:

1. Read e-commerce data.
2. Analyze inventory and sales signals.
3. Identify business opportunities.
4. Delegate tasks to specialist agents.
5. Generate recommendations.
6. Require approval before risky actions.
7. Execute approved simulated actions.
8. Record the outcome.
9. Record outcomes for audit and future human review; no automatic learning is implemented.

---

## 3. Specialist Agents

CartPilot contains four specialist agents.

### Pricing Agent

Responsibilities:

- Analyze product pricing.
- Analyze sales velocity.
- Analyze inventory.
- Detect pricing opportunities.
- Recommend price changes.
- Respect minimum and maximum price limits.

Initial mode:

READ-ONLY RECOMMENDATIONS

---

### Restock Agent

Responsibilities:

- Monitor inventory.
- Analyze sales velocity.
- Estimate demand.
- Detect possible stockouts.
- Recommend reorder quantities.
- Respect reorder limits.

Initial mode:

READ-ONLY RECOMMENDATIONS

---

### Promotion Agent

Responsibilities:

- Detect slow-moving products.
- Identify promotion opportunities.
- Recommend discounts.
- Recommend campaigns.
- Respect discount limits.

Initial mode:

RECOMMENDATION ONLY

---

### Listing Agent

Responsibilities:

- Analyze product listings.
- Detect missing or weak information.
- Recommend title improvements.
- Recommend description improvements.
- Recommend metadata improvements.

Initial mode:

RECOMMENDATION ONLY

---

## 4. Master Orchestrator

The Master Orchestrator is responsible for:

1. Receiving merchant goals.
2. Reading current store state.
3. Creating a business context.
4. Determining which agents should run.
5. Calling specialist agents.
6. Combining agent recommendations.
7. Detecting conflicts.
8. Applying business rules.
9. Producing an action plan.
10. Requesting human approval where required.
11. Producing candidates for separately approved local/simulated actions.
12. Recording results.

The orchestrator must NOT blindly execute an agent recommendation.

---

## 5. Safety Rules

Never execute an action without validating:

- price limits
- discount limits
- inventory limits
- reorder limits
- merchant policies
- approval requirements

Every action must have:

- action_id
- agent
- product_id
- reason
- proposed_change
- expected_effect
- risk_level
- approval_status
- timestamp

---

## 6. Development Rules

Before writing code:

1. Read this file.
2. Read PLAN.md.
3. Read ARCHITECTURE.md.
4. Read the current PHASE file.
5. Inspect existing code.
6. Do not rewrite working code unnecessarily.
7. Implement only the current phase.
8. Run tests.
9. Fix failures.
10. Update documentation.
11. Report completed work.

---

## 7. Agent Development Rule

Each specialist agent must be independently testable.

Do not create one giant agent.

Use:

- clear inputs
- clear outputs
- typed schemas
- deterministic business rules
- LLM reasoning only where appropriate

---

## 8. AI Rule

LLMs must not directly manipulate the database.

LLMs produce structured decisions.

Application code validates decisions.

Tools perform actions.

Architecture:

LLM
 ↓
Structured Decision
 ↓
Validation
 ↓
Approval
 ↓
Tool
 ↓
Database/API

---

## 9. Current MVP Strategy

Start with mock e-commerce data.

Do not connect production Shopify APIs in Phase 1.

The MVP should demonstrate:

Inventory
→
Orders
→
Agent reasoning
→
Recommendation
→
Approval
→
Simulated action
→
Audit log

---

## 10. Definition of Done

A phase is complete only when:

- implementation exists
- tests exist
- tests pass
- API works
- errors are handled
- documentation is updated
- no secrets are committed
- git status is clean except intended files

---

## 11. Forbidden Actions

Do not:

- expose API keys
- commit .env
- delete working features without approval
- replace architecture without approval
- introduce unnecessary dependencies
- connect production APIs without approval
- execute irreversible merchant actions automatically

---

## 12. Current Phase

Read:

phases/PHASE_14.md

Do not move to the next phase until the current phase passes verification.

## Final submission boundary

Phase 14 packages the verified MVP. Product specialists are deterministic; SENSE/DECIDE
are implemented, ACT is guarded local/simulated, and LEARN currently records history
without training. FINAL_STATUS.md is authoritative for implemented/simulated/read-only
classifications. After Phase 14, stop feature development unless a real defect or
explicit project-guide request justifies further work.
