# PHASE 09 — GUARDED ACTIONS

Status: COMPLETE. Phase 9 introduces guarded, human-approved execution.
Agents still cannot directly execute merchant actions. Phase 10 is not implemented.

## Workflow and state machine

Typed recommendation → immutable action payload → policy validation → human
approval/rejection → separately confirmed execution → immediate policy revalidation
→ local mutation or simulation → persistent audit.

Supported transitions:

- pending → validated → awaiting_approval
- pending → failed when creation policy blocks the proposal
- awaiting_approval → approved or rejected
- approved → executing → executed or failed

Rejected, failed, cancelled and executed actions cannot be approved again. Repeating
execution of an executed action returns the existing result/timestamp without a
second mutation. A policy-blocked execution remains approved with a blocked result;
it can run only after another deliberate confirmation and a successful fresh check.
There is no scheduler, automatic retry or approval bypass.

## Supported actions

| Action | Phase 9 execution | Current-state policy |
| --- | --- | --- |
| price_change | Update local selling price and append PriceHistory | Active product, unchanged source price/cost, cost/margin floor, configured increase/decrease caps, cent precision |
| restock | Record simulated replenishment request | Positive bounded quantity, fresh demand and replenishment need; never increase inventory |
| promotion | Record simulated discount proposal | Discount cap/arithmetic, retained gross margin, unchanged price/cost, fresh inventory/stockout and demand checks; never change base price |
| listing_update | Update local title/description | Unchanged title/description/category/SKU, deterministic grounded content, genuine content change; never write a marketplace |

The validator rejects unsafe values rather than silently changing the approved
payload. Limits reuse existing environment settings and agent rules. All actions,
including low risk actions, require human approval and separate execution.

## APIs

All routes have the `/api/v1` prefix:

| Method | Route | Input |
| --- | --- | --- |
| POST | /actions | merchant_id plus saved recommendation_id **or** agent and typed recommendation |
| GET | /actions | merchant_id, offset, limit (maximum 100) |
| GET | /actions/{id} | merchant_id |
| POST | /actions/{id}/approve | merchant_id, actor, optional comment |
| POST | /actions/{id}/reject | merchant_id, actor, optional comment |
| POST | /actions/{id}/execute | merchant_id, actor, optional comment, boolean confirm: true |
| GET | /action-history | merchant_id, offset, limit (maximum 200) |

Development actor defaults to `development-merchant`. Ownership checks verify the
requested merchant against recommendation and product ownership. This is scope
validation, not authenticated identity. Write endpoints are disabled unless
ENVIRONMENT is development or test. Production authentication is future work.

Successful requests return complete ActionResponse objects. Creation-time policy
blocks return a failed action with policy violations. Execution-time policy blocks
return an approved action with result.outcome `blocked`. Clients must inspect policy
and result, not just HTTP 200. Invalid transitions/unapproved execution return 409,
foreign scope 403, missing records 404, invalid payloads/confirmation 422 and handled
storage errors 503. Execution failures return a failed action with sanitized details.

## Concurrency, idempotency and transactions

A unique workflow_key deduplicates saved sources and canonical inline proposals.
Referencing an inline-created recommendation by its saved ID returns the same action.
Deduplication persists after terminal states: regenerate a genuinely new proposal
rather than replay a failed/rejected source. Existing legacy action rows retain a
null workflow_key and are not exposed as executable guarded actions.

PostgreSQL row locks protect action, product and inventory snapshots. Atomic
compare-and-set updates protect approval and execution claims on engines without
row-lock support. Price/listing mutations additionally compare approved source
values in their UPDATE conditions. No action can mutate twice concurrently.

Execution claims and start events are in an outer transaction. Product mutation,
PriceHistory, executed state and completion audit share a savepoint. Executor or
completion-audit failure rolls back those changes together; the outer transaction
then records failed state and a sanitized failure audit. If database availability
also prevents writing the failure audit, the entire transaction rolls back; a
persistent failure event cannot be guaranteed during database unavailability.

## Audit

Persistent AuditLog events include recommendation creation/selection, action
creation, policy validation, validated/awaiting approval, approval/rejection,
execution start, completion, block and failure. Metadata includes action/product,
agent, state and performed_by; review comments and policy violations are captured.
Local mutation completion records before/after values. Audit timestamps are UTC.
Structured event logging contains event and record IDs, never credentials.

## Frontend

Products and Recommendations expose Create Action for Review. AI Manager exposes
individual coordinated proposals and disables deferred/hold proposals. Analysis
never creates or executes actions automatically.

Approvals displays product, agent, reason, proposed change, risk, policy, actor,
optional review comment and execution mode. Approve and Reject are functional.
Approval leaves data unchanged. Execute Approved Action opens a focus-managed
confirmation dialog with Cancel and Execute. Blocked/failed/executed outcomes and
before/after details are displayed. Action History shows scoped persistent events,
actor, state, UTC timestamp and expandable details. Both pages support refresh and
pagination. Merchant changes clear previous action/history views.

## Migration and running

From backend, activate the existing environment and apply:

```bash
venv/bin/alembic upgrade head
venv/bin/pytest -q
```

Revision `9a10guarded` extends the existing Action table's status check, adds unique
nullable workflow_key, risk_level, created_at and updated_at. Existing rows survive
and remain non-executable. Downgrade maps new-only lifecycle states to cancelled
before restoring the old check, and removes new columns. Upgrade/downgrade were
verified on an isolated SQLite database. Live PostgreSQL deployment was not tested.
The developer's existing database was not modified by verification.

From frontend:

```bash
npm test -- --run
npm run build
```

No lint script is configured; no new dependencies were added.

## Verification and demo results

41 Phase 9 backend tests; 333 total backend tests. 48 frontend tests (9 new guarded
workflow tests); production build passes. Coverage includes all action kinds,
unsafe policies, source tampering, stale price/cost/listing/inventory, strict boolean
confirmation, merchant scope, invalid transitions, concurrent execution,
creation/execution deduplication, rollback and migration preservation.

An isolated in-memory HTTP API demo exercised these results. No live merchant data
was touched. See [recorded results](../docs/examples/guarded-actions-demo.json).

1. Safe price: 999.00 → 1048.95. Approval retained 999.00; confirmed execution changed
   price, created exactly one PriceHistory row and completion audit.
2. Unsafe price: 999.00 → 1499.00 blocked by maximum increase; unchanged price/history.
3. Rejected action: execution returned 409; price stayed 999.00.
4. Duplicate execution: original executed result/timestamp returned; one history row.
5. Stale approved promotion: reducing inventory to two units blocked execution for
   current stockout risk; base price remained 1499.00 and no price history was added.

Manual dashboard walkthrough: Products → analyze → Create Action for Review →
Open Approvals → optional comment → Approve → verify no data change → Execute
Approved Action → Cancel or Execute → inspect result, Products Price History and
Action History. Use isolated mock data for inventory-changing demo setup.

## Limitations and next phase

Restock and promotion remain simulations. Price/listing mutations are local only.
Development actors are not authenticated users. No external commerce/supplier/ad
writes exist. No automatic retries or unattended execution exist. PostgreSQL locks
are implemented but concurrency validation ran on SQLite. The typed guarded tool
boundary is ready for later orchestration work without granting agents write access.
Stop after Phase 9; Phase 10 remains future work.
