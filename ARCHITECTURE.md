# CARTPILOT ARCHITECTURE

## High Level

Frontend
    ↓
FastAPI
    ↓
Master Orchestrator
    ↓
Specialist Agents
    ↓
Tools
    ↓
Database / Store APIs

---

## Frontend

React + TypeScript + Vite + Tailwind

Responsibilities:

- dashboard
- products
- inventory
- recommendations
- approvals
- agent activity
- action history

Frontend must never contain AI business logic.

---

## Backend

FastAPI

Responsibilities:

- authentication
- API endpoints
- business logic
- agent execution
- policy validation
- database access

---

## Agent Layer

LangGraph manages agent workflows.

Agents:

pricing_agent
restock_agent
promotion_agent
listing_agent

Master:

orchestrator

---

## Database

PostgreSQL

Tables:

merchants
products
inventory
orders
order_items
price_history
agent_runs
recommendations
actions
approvals
audit_logs

---

## AI Layer

LLM is responsible for:

- reasoning
- classification
- summarization
- recommendation generation

Traditional Python code is responsible for:

- validation
- limits
- calculations
- database changes
- permissions
- security

---

## Tool Layer

Tools:

get_products
get_inventory
get_orders
get_sales_velocity
get_price_history
recommend_price_change
recommend_restock
create_promotion
update_listing
execute_action

---

## Safety Architecture

Agent
 ↓
Decision
 ↓
Policy Validator
 ↓
Approval
 ↓
Action Executor
 ↓
Audit Log