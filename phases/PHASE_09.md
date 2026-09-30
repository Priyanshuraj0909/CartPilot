# PHASE 09 — GUARDED ACTIONS

## Objective

Allow approved actions.

Architecture:

Recommendation
↓
Policy Validator
↓
Approval
↓
Action Executor
↓
Audit Log

## Policies

Maximum price change
Maximum discount
Maximum reorder quantity

## Approval

Every risky action requires approval.

## Audit

Record:

who
what
when
why
agent
before
after
result