# CARTPILOT MASTER PLAN

## Phase 1 — Foundation

Goal:

Create the project structure and development environment.

Deliverables:

- Git repository
- FastAPI backend
- React frontend
- PostgreSQL
- Docker Compose
- environment configuration
- health check
- basic CI/testing

---

## Phase 2 — Data Layer

Build:

- Product model
- Inventory model
- Order model
- Merchant model
- Price history
- Action log

Create mock store data.

---

## Phase 3 — Pricing Agent

Build:

Pricing Agent

Input:

- product
- current price
- sales velocity
- inventory
- historical data

Output:

Structured pricing recommendation.

Example:

{
  "product_id": "SKU-001",
  "current_price": 999,
  "recommended_price": 1049,
  "reason": "High sales velocity and low inventory",
  "confidence": 0.86,
  "risk_level": "medium"
}

---

## Phase 4 — Restock Agent

Build:

Restock Agent.

Detect:

- low inventory
- high sales velocity
- potential stockout

Produce:

- recommended reorder quantity
- estimated stockout date
- reason
- confidence

---

## Phase 5 — Master Orchestrator

Implement:

Sense
↓
Context
↓
Agent selection
↓
Parallel agent execution
↓
Conflict resolution
↓
Policy validation
↓
Action plan

---

## Phase 6 — Frontend

Build merchant dashboard.

Dashboard sections:

- Revenue
- Orders
- Inventory
- Alerts
- AI recommendations
- Agent activity
- Pending approvals
- Action history

---

## Phase 7 — Promotion Agent

Detect:

- slow movers
- declining sales
- promotional opportunities

Recommend:

- discount
- campaign
- target products

---

## Phase 8 — Listing Agent

Analyze:

- title
- description
- attributes
- SEO metadata

Produce listing improvement recommendations.

---

## Phase 9 — Guarded Actions

Introduce:

- approval system
- action policies
- price limits
- discount limits
- inventory limits
- audit logs

Allow approved simulated actions.

---

## Phase 10 — Cross-Agent Intelligence

Implement:

Pricing
+
Restock
+
Promotion
+
Listing

under the Master Orchestrator.

Resolve conflicts.

Create unified merchant goal execution.

---

## Phase 11 — Real E-Commerce Integration

After the mock system is stable:

Add Shopify integration.

Use read-only access first.

Then guarded write operations.

---

## Phase 12 — Final Testing

Perform:

- unit testing
- integration testing
- API testing
- agent testing
- frontend testing
- security testing
- failure testing
- end-to-end testing