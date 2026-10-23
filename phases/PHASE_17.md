# Phase 17 — Buyer commerce extension

Authorized on 23 October 2026: extend CartPilot with shopping capabilities comparable
to the referenced project, preserve existing merchant operations, and publish verified
source and README changes to the existing GitHub repository.

Scope: opt-in public storefront, isolated expiring shopper sessions, optional Gemini
structured intent, explainable hybrid recommendations, server-priced bounded carts,
explicit approval, test checkout, hash-linked mandates/audit, merchant growth console,
catalog CSV onboarding and an MCP adapter. No friend source is copied.

Boundaries: no live charges, supplier orders, autonomous price/promotion changes or
Shopify writes. Simulation is separate from recorded sales. Model/API credentials
remain backend-only. Provider failures must preserve safe, reviewable state.

Implemented the scoped storefront, strict shopper/cart contracts, server-owned pricing,
15-minute quotes, explicit approval, separately confirmed simulation/test checkout,
SHA-256 mandate chain, signed Razorpay test settlement, atomic CSV catalog import,
merchant growth controls and MCP draft-shopping adapter. Hybrid ranking includes
explicit bounded 16-dimensional Item2Vec and optional fingerprinted Gemini embeddings.
No dependencies were added and no referenced-project source was copied.

Verification: 688 backend tests; 158 frontend tests; TypeScript/Vite build; SQLite
upgrade/downgrade/re-upgrade; all three disposable PostgreSQL concurrency tests; real
Chrome selection/review/approval/simulation/audit and 390px responsive layout passed.
Three new real browser captures and structured evidence are committed. Configured
hosted database migrated to `17_commerce`; existing aggregate row counts preserved.

Live providers/desktop MCP clients, durable browser cart recovery, automatic payment
reconciliation, refunds, fulfillment, external messaging, measurable ranking lift and
production readiness remain unverified or unimplemented as described in the guide.
See docs/BUYER_COMMERCE.md and TEST_SUMMARY.md. Publication targets the existing Priyanshuraj0909/CartPilot main branch;
current remote results are available in GitHub Actions and commit deployment checks.
