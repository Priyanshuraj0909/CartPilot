# Phase 19 — Cart integrity, reservations and initial hardening

Status: PLANNED; implementation has not started. Audit/planning prerequisite is complete.
The previous Phase 18 release and migration remain intact.

Current problems: persisted carts check available stock without allocating it; deployed
test checkout is not a fulfillment system. Fresh advisory scans identify dependency
risks, and public request budgets/body limits need a consistent review.

Read [audit](../REPOSITORY_AUDIT.md), [master plan](../UPGRADE_MASTER_PLAN.md),
[architecture](../UPGRADE_ARCHITECTURE.md), [roadmap](../UPGRADE_ROADMAP.md),
[test strategy](../UPGRADE_TEST_STRATEGY.md) and [progress](../UPGRADE_PROGRESS.md)
before implementation. Affected paths, smallest solution, UI scope, failure/concurrency
checks and suggested commit messages are specified in the Phase 19 roadmap section.

Required exit: dependency findings remediated or explicitly assessed; current workflows
preserved; opt-in tenant-scoped sandbox leases cannot double allocate, expire/release once
and survive retries/crashes; defaults never decrement physical inventory from test payments;
migrations preserve existing rows; relevant tests/build/docs and deployment checks pass.

Do not introduce order fulfillment, ML training, live payments or a framework migration
as incidental work in this phase. Subsequent phases have separate gates.
