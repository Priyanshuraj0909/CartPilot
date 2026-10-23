# Phase 18 — Commerce workflow parity

User-authorized on 23 October 2026: implement the functional capabilities present in
VishalDhariwal/CartPilot, adapted to this repository's existing architecture. Prior
authorization to update GitHub/README persists. Preserve merchant account scope and
application validation; models must not directly mutate merchant records or authorize
financial actions. Provider credentials remain backend-only.

Checklist (implementation and verification tracked in docs/COMMERCE_PARITY.md):

- Conversational buyer journey, saved sessions, cart editing, substitutes and upsells.
- Payment status/reconciliation, guarded recovery links/offers, cancellation and refunds.
- Category compatibility generation/overrides, growth rules, ranking/lift previews.
- Persistent scheduled growth controls, seasonal/weather context and audit dashboard.
- API/CSV/demo onboarding, optional provider failover, 64-dimensional co-purchase model
  and optional local semantic embeddings.
- Expanded MCP tools with application-enforced confirmation boundaries and browser handoff.
- Regression/failure/concurrency tests, frontend build, documentation, GitHub publication.

Live charges and autonomous financial authorization are excluded from the default
configuration. Equivalent feature behavior does not require copying the friend's code,
unsafe authorization shortcuts or cloud-provider-specific infrastructure.

Implemented all checklist groups with the explicit adaptations in the capability
guide: financial model tools hand off to browser confirmation; metrics do not invent
causal revenue; catalog clear archives history; optional providers/worker require
configuration. New domain operations are isolated from real sales and fulfillment.

Verification: 738 backend tests, 174 frontend tests, production build, five disposable
PostgreSQL concurrency checks, migration preservation and real Chrome desktop/mobile
workflow pass. The browser exercise includes chat, recovery offer, separate approval/
simulation, partial refund, return review and reload restoration. Optional model/
payment/provider paths use mocks; no live financial validation is claimed.
