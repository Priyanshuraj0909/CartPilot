# CartPilot project report and presentation content

Working title: **CartPilot — A Multi-Agent E-Commerce Decision and Operations Management System**.
Tagline: **The AI Manager Sitting on Top of Your Inventory**.
Use institution-required formatting; add your real student/team/guide/institution details.
No author identity, experimental business improvement or institutional approval is fabricated.

## 1. Abstract draft (193 words)

E-commerce operations require coordinated decisions about product pricing, inventory
replenishment, promotions and catalog quality. When these decisions are made independently,
a discount may increase demand for a product already facing stockout risk, while poor
listing information may be mistaken for a pricing problem. CartPilot addresses this
coordination problem through a modular, recommendation-first decision-support system.
Four deterministic specialist agents analyze shared merchant data and produce structured,
explainable recommendations. A Master Orchestrator combines their outputs according to
merchant goals, identifies conflicts, synergies and dependencies, and constructs a bounded
priority plan. Proposed operations pass through typed policy validation, human approval,
separate execution confirmation and current-state revalidation. Price and listing changes
apply only to local data; replenishment and promotion execution are simulated and audited.
A read-only Shopify integration imports store data without modifying the external store.
The implementation uses a React and TypeScript frontend, a FastAPI backend and relational
persistence with versioned migrations. Verification includes unit, integration, failure,
workflow and browser checks. The contribution is an explainable coordination and guarded
execution design rather than a trained forecasting model. Current limitations include
simulated external execution, absent production authentication and no autonomous learning.
Measured revenue improvements are not claimed.

## 2. Introduction

Describe decisions above store data rather than a replacement commerce storefront.
Motivate explainable coordination and merchant review. Define recommendation/action/
approval/execution separately. Cite sources; distinguish general motivation from measured
findings. Project description and capability classifications: FINAL_STATUS.md.

## 3. Problem statement draft

Pricing, replenishment, discounting and listing maintenance are interdependent operational
tasks. Fragmented decisions can stimulate demand for constrained stock, retain excess
inventory or treat incomplete product information as a pricing issue. Manual review
requires reading several signals and reconciling recommendations. The project investigates
whether an explainable modular workflow can centralize these signals, prioritize operational
review and prevent unsafe local changes. These are motivating concerns, not quantified
business losses measured by this project.

## 4. Objectives

1. Centralize scoped product/order/inventory/history data and usable signals.
2. Produce four specialized explainable, typed recommendations.
3. Coordinate merchant goals, conflicts, synergies, dependencies and priorities.
4. Protect changes with policies, human approval, revalidation and audit.
5. Import Shopify data through read-only, bounded, idempotent synchronization.
6. Provide reproducible tests and a reliable demonstration with honest limitations.

## 5. Literature / existing systems

Review commerce data APIs, typed web services, relational consistency and explainable
rule-based decision-support approaches. Use primary documentation references below for
implemented technologies. If the institution requires peer-reviewed papers, add papers you
have actually read and cite their precise methods/limits. Do not invent literature results
or assert CartPilot outperforms commercial systems; no competitive benchmark was run.
Separate a commerce platform's capabilities from CartPilot's narrower integration scope.

## 6. Proposed system

A modular layer above demo/Shopify data with four specialists and a coordinating Master
Orchestrator. Present the verified capability table in FINAL_STATUS.md and stakeholder
flow in DEMO_SCRIPT.md. Human-controlled local operations are the actual execution scope.

## 7. Methodology

**Sense:** sync/read products, orders, available stock, price history and listing text;
calculate shared velocities/coverage/quality. **Decide:** deterministic specialists and
goal-based coordination. **Act:** policies, approval, confirmation, fresh validation and
local/simulated execution. **Learn:** record outcomes/audit for review; no automatic model
updates, reinforcement learning or adaptive demand model is implemented.

## 8. System architecture

Use ARCHITECTURE.md's Mermaid diagram and describe recommendation, coordination, approval,
execution and external read-only boundaries. Backend Python calls coordinate specialists;
there is no distributed LLM agent network. Browser calls only backend APIs. Redis optional.

## 9. Algorithms / techniques

Use docs/ALGORITHMS.md verbatim as the technical source: rule systems, velocity/coverage,
lead-time demand, ceil safety stock/buffer, Decimal guardrails, retained-margin discounts,
listing checks, goal weights, conflict rules, finite-state workflow and idempotency.
Explain that confidence/priority are heuristics, not calibrated predictions. Include source
paths so examiner calculations can be checked. Pricing markup differs from gross margin.

## 10. Database design

Entity summary and ownership/external mappings: docs/API_DATABASE_SECURITY.md.
Add a schema figure from actual models if institution requires it; do not add nonexistent
customer/auth/supplier models. AgentRun exists but session UI is not persisted through it.
Describe foreign keys, unique identities, Decimal money and UTC timestamps.

## 11. Implementation and exact stack

Verified local runtime and checked-in constraints/package-lock:

| Area | Verified version / target |
| --- | --- |
| Runtime | Python 3.12.7, Node 26.10.0 locally; Docker builder/CI target Node 24 |
| Frontend | React 18.3.1, TypeScript 5.9.3, Vite 5.4.21, Tailwind CSS 3.4.19, Lucide 0.441.0 |
| Backend | FastAPI 0.142.2, Pydantic 2.13.5, SQLAlchemy 2.1.1, Alembic 1.20.0, Uvicorn 0.54.0 |
| Persistence | PostgreSQL 16 container target; isolated PostgreSQL 17.11 verified in Phase 13; asyncpg 0.31.0 |
| Isolated demos/tests | SQLite via aiosqlite 0.22.1 |
| Optional diagnostics | Redis server 7 container target; Python Redis client 8.1.0 |
| Testing | pytest 9.1.1, pytest-asyncio 1.4.0, Vitest 2.1.9, jsdom 25.0.1, React Testing Library 16.3.3 |
| Integration | httpx 0.28.1; Shopify Admin GraphQL, central configured API version 2026-10, read queries only |

Dependency constraints describe the tested environment, not latest-version recommendations.
Configuration/deployment: DEPLOYMENT.md. No OpenAI/Gemini/LLM SDK is used by agents.

## 12. Testing

Use TEST_SUMMARY.md: 560 backend tests, 76 frontend tests, successful TypeScript/Vite
build, no configured lint. Explain isolated fixtures, synthetic Shopify transport,
state/ownership/error testing, bootstrap and browser verification. Do not call test
count “accuracy”. PostgreSQL execution is verified but concurrency stress is not.

## 13. Results / demonstration

Use the four-product Balanced Growth output, screenshots and JSON evidence. Demonstrated:
critical restock, declining-sales discount, factual listing review, deferred competing
pricing/discounts, separate approval and execution, unsafe-change block and persistent
audit. Mocked Shopify import is idempotent/read-only; it is not a real-store experiment.
Report qualitative behavior, not unmeasured revenue lift, stockout reduction or time saved.

## 14. Security and guardrails

Discuss scope validation vs missing authentication; typed payloads, policies, human review,
source checks, transactions, duplicate prevention, audit, secret boundaries and safe
errors. Production gates write/integration routes. CORS is not identity/security proof.

## 15. Limitations

Deterministic heuristics without advanced forecasting; assumptions about lead time/demand;
text heuristics without verified attribute truth or SEO validation; local price/listing
mutation and simulated restock/promotions; Shopify read-only and live store unverified;
no production auth/RL; bounded 100-product scope; some per-product aggregates still scale
linearly; containers/cloud/provider TLS/remote CI and locking stress unverified.

## 16. Future scope

Validated time-series forecasting, supplier adapters, authenticated merchant identity,
rate controls, carefully authorized Shopify writes, additional commerce adapters,
real outcome feedback and measured promotion optimization. All are future proposals.

## 17. Conclusion draft

CartPilot demonstrates explainable multi-domain e-commerce coordination with an explicit
human-controlled execution boundary. The verified prototype produces structured priority
plans, exposes conflicts and prevents unsafe local changes while retaining audit evidence.
It is suitable for a trusted academic demonstration. Broader production/external execution
requires the documented identity, infrastructure and forecasting work; measured business
impact has not been established.

## 18. References

Primary technology references reviewed 3 October 2026. Cite in your institution's format;
these document tools, not evidence of CartPilot business performance.

- [FastAPI documentation](https://fastapi.tiangolo.com/) — typed API/OpenAPI design.
- [SQLAlchemy asyncio documentation](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html) — async ORM/session usage.
- [Alembic migration tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html) — versioned schema workflow.
- [Pydantic validation documentation](https://pydantic.dev/docs/validation/latest/get-started/) — schema validation concepts.
- [React documentation](https://react.dev/) — component-based frontend.
- [Shopify GraphQL Admin API](https://shopify.dev/docs/api/admin-graphql/latest) — external API; CartPilot uses only a closed read-only subset.
- CartPilot source/phase docs and TEST_SUMMARY.md — project-specific verification evidence.

## Presentation content outline — 12 slides, no PPT generated

| Slide | Content / evidence |
| --- | --- |
| 1. Title | Name, tagline, real team/guide/institution |
| 2. Problem | Fragmented decisions; stock/discount/catalog conflict example |
| 3. Objectives | Explainable coordination + human-controlled safety |
| 4. Proposed solution | Scoped signals → specialists → advisory queue |
| 5. Architecture | ARCHITECTURE Mermaid, read-only/local/simulated boundaries |
| 6. Four agents | Rules/formulas and screenshots 04–07 |
| 7. Master Orchestrator | Four-product Balanced Growth, priority/conflict screenshots 08–10 |
| 8. Guardrails and approval | Separate review/confirm/revalidate; screenshots 11–12,14 |
| 9. Demo/results | 999→1048.95 local outcome, audit; mocked Shopify label explicit |
| 10. Testing | Exact 560/76/build/bootstrap/browser results, no accuracy/uplift claim |
| 11. Limits/future | Deterministic, simulated external actions, no auth/learning; future work separated |
| 12. Conclusion | Engineering contribution, honest boundaries, questions |
