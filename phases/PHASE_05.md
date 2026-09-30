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