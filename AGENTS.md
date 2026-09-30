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