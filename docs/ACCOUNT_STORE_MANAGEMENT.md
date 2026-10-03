# Account and store management continuation

The user explicitly requested development beyond the Phase 14 submission boundary.

Implemented: account signup/login/logout, server-stored revocable 8-hour sessions,
scrypt password hashing with individual salts, hashed session tokens, production
read-API authentication, server-bound merchant scope including legacy unscoped product
analysis, filtered merchant listings, authenticated product create/edit/archive,
price-history preservation, atomic bounded sales import with reference deduplication,
sales ranking/revenue summaries and on-demand low-stock alerts.

Run migrations before starting: `python -m alembic upgrade head` adds `15_accounts`.
Existing seeded merchants cannot be claimed by signing up with their email; signup
creates a separate new store. Add products through Products, then upload sales CSV.
Required headers: `reference,product_id,quantity,unit_price,ordered_at`. One product
per reference, up to 500 rows, timezone-aware past timestamps. This is a simple CSV
format; quoted commas are not supported. Import does not adjust physical inventory.
Archive retains historical orders. Externally sourced products must be managed in
the source store. Price edits record history and remain subject to stale action checks.

Production always requires authentication. For authenticated local development set
backend REQUIRE_AUTH=true and frontend VITE_REQUIRE_AUTH=true, then restart/rebuild.
Anonymous seeded demos remain supported only in development/test by default. The
frontend stores the session token in sessionStorage and sends Authorization headers.
Logout revokes the session server-side. HTTPS is required for hosted deployment.

Production action writes and Shopify routes remain blocked even for logged-in users.
No supplier orders, Shopify writes, real campaign launches, email provider, password
recovery, email verification or admin console was added. Low-stock notifications are
computed on demand, not persistent delivered email. Ingress rate limits and broader
security/browser/load audits remain necessary before general public launch.

Historical report/PPT and Phase 14 results describe the previous verified MVP; this
continuation supersedes their authentication/product-management limitations only.
Old anonymous deployment smoke commands must now supply an authenticated bearer token
for protected business reads; root health remains public.

Verification: **569 backend tests passed in 17.18 seconds**, including account lifecycle,
expiry, foreign-store denial, CRUD/archive, repeat/conflicting imports, authenticated
production restrictions and five-product new-store orchestration. **78 frontend tests**
passed across 10 files, including account signin/logout. TypeScript/Vite build and fresh
SQLite migrations through 15_accounts passed. No new browser/Lighthouse/load test or
managed PostgreSQL migration was performed; changes remain local and unpushed.

Deployment smoke accepts an optional CARTPILOT_SMOKE_TOKEN process environment variable.
Use a fresh account session and at least one owned product; do not put tokens in command
arguments or checked-in files. The smoke keeps its authenticated production 403 checks.

## Visible workspace update — 4 October 2026

Navigation now includes Manage Store, Sales & Insights and Notifications. Account entry
is visible in anonymous demo workspaces; production builds always present account access.
Sales ranking and stock alerts load on page entry; CSV sample download and product IDs
are visible. Footer version marker: `Merchant workspace v15.1`.

Verification: 583 backend tests and 87 frontend tests passed; production build passed.
A fresh isolated real-browser walkthrough created an account and product, uploaded a
sales CSV, displayed 40.00 recorded revenue and checked notifications/mobile layout.
The configured Neon DB was read-only checked at revision 15_accounts. This does not
prove the Vercel backend uses that same database. Requests to the supplied public frontend
URL timed out from the execution environment; live deployment has not been certified.
# Dashboard shortcuts

The dashboard now exposes product management, sales import/insights and stock
notifications directly in a merchant workspace panel. New accounts start with an
empty store; add products and import sales before expecting populated revenue or
product recommendations. These pages are also available from the sidebar.

## Account screen design

Login and signup use a responsive CartPilot brand panel and a dedicated vertical
form. Store name has its own labeled input and helper text. Inputs include autofill
hints; password visibility uses a named toggle; submission disables the fieldset;
errors use an alert; keyboard focus is visible. Desktop and 390px mobile layouts
were inspected in a real browser (no horizontal overflow or browser errors).
