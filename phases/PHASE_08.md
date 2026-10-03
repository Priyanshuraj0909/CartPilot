# PHASE 08 — LISTING AGENT

Status: COMPLETE. Phase 9 has not been implemented.

The Listing Agent recommends listing improvements only. It never publishes or updates
product listings automatically. No Product fields, approvals, commerce APIs or actions
are written by recommendation endpoints or orchestration. No new database fields,
migration, dependencies, LLM, or marketplace integration were introduced.

## Inputs and implementation

Reads existing Product.name, description, category, SKU, selling_price and status.
ListingSignals is a typed immutable read snapshot, not a new database model. Product
name is the current title. Missing descriptions/categories are safely analyzed; empty
or HTML-only titles and invalid numeric source data return 422. Listing-only analysis
requires no inventory, order history or sales analytics. Reads suppress autoflush.

Modules: agents/listing_agent.py, services/listing/signals.py, quality.py, generator.py,
and schemas/listing.py. The agent can run independently or from a preloaded snapshot.

## Quality checks and score

Default configuration in Settings and .env.example:

```text
MIN_TITLE_LENGTH=10
MAX_TITLE_LENGTH=120
MIN_DESCRIPTION_LENGTH=80
MAX_DESCRIPTION_LENGTH=2000
LISTING_POOR_QUALITY_THRESHOLD=0.6
```

MIN_DESCRIPTION_LENGTH is a diagnostic threshold, not permission to invent enough text
to fill a target length. Recommended descriptions must be nonblank and within the
maximum. Recommended titles must meet configured minimum/maximum bounds. Policies
reject inverted bounds; title maximum cannot exceed the existing 255-character model.

Checks:

- Title length, generic or two-word titles, and formatting/whitespace/markup cleanup.
- Missing, short, overly long or duplicate-title descriptions and formatting issues.
- Lightweight category alignment from explicit words: Electronics, Clothing/Apparel,
  and Home/Home & Kitchen. Clear contrary vocabulary triggers a review, not an
  automatic category change. Other categories are unverified, not presumed incorrect.
- Mentioned attributes: electronics connectivity/power/compatibility/dimensions;
  clothing material/size/care; home material/dimensions. These are optional details
  to verify where applicable, not required facts or a full taxonomy.

The score is deterministic and bounded in [0,1]:

`0.25 × title checks passed/3 + 0.35 × description checks passed/4 +
0.25 × attribute mention fraction + 0.15 × category alignment`

Title checks: length within bounds, more than two distinct words/non-generic name,
and clean formatting. Description checks: present, length within bounds, not equal to
title ignoring terminal punctuation/case, and clean formatting. Category alignment is
1 for consistent, 0.5 for unverified, 0 for missing/inconsistent. Unsupported attribute
categories receive neutral 0.5 completeness. Scores round to two decimals. This is a
content completeness heuristic, not model accuracy or marketplace SEO ranking.

No marketing-heavy copy is required. Suggestions request clear factual detail and
verified usage benefits rather than claiming benefits the source does not supply.
Recommended keywords are deduplicated sorted words from existing title/category,
excluding a small stopword set; no new keywords or product specifications are invented.

## Grounding, confidence and risk

Generation normalizes whitespace and extracts plain text while removing script/style
contents. Short low-information titles may append an entire short source description,
including negations; it never extracts feature fragments or drops qualifying sentences.
If still too short, known category/SKU can supplement the title. Long titles use a
known identifier or a neutral Product listing label rather than cutting a claim.
Impossible configured bounds fail safely.

Descriptions retain existing factual text. Missing/duplicate descriptions receive only
known title, category and SKU. Overly long descriptions use a merchant-verification
message rather than truncating away qualifiers. Good listings remain unchanged.
Missing attributes are shown as “Verify and add … details if applicable,” never filled
with guessed specs. HTML is not executed by the frontend; text comparisons use normal
React rendering. There is no external factual verification of existing merchant claims.

Confidence: 0.45 base + 0.20 when description exists + 0.15 when category exists + 0.10
when SKU exists, capped at 0.90. Extremely sparse generic-title/no-description or
no-description/no-category inputs receive 0.20. Confidence measures available context,
not factual truth, accuracy, or predicted conversion uplift.

Risk: high for extremely sparse input or category contradiction; medium for missing or
length-bounded text requiring substantial content review, or quality below 0.60;
otherwise low. Typed output validates finite bounded metrics, enums, nonblank content
and output lengths. The orchestrator independently recomputes the grounded result and
rejects altered content or metrics, including unsupported feature injections.

## API and persistence

`POST /api/v1/listing/recommend`

Request: strict positive product_id and optional merchant_id. The frontend supplies
merchant_id. Missing product returns 404; ownership mismatch 403; invalid data/bounds
422; SQLAlchemy errors sanitized 503. Missing description returns advice, not a failure.
These merchant checks do not implement authenticated identity binding.

Real recorded API request:

```json
{"product_id": 1, "merchant_id": 1}
```

Response excerpt from the existing headphones seed:

```json
{
  "product_id": 1,
  "current_title": "Wireless Noise-Canceling Headphones",
  "recommended_title": "Wireless Noise-Canceling Headphones",
  "current_description": "Premium over-ear headphones with 40h battery.",
  "recommended_description": "Premium over-ear headphones with 40h battery.",
  "issues": ["Description is too short", "Useful product attributes are not mentioned"],
  "suggestions": [
    "Provide clear factual details and verified usage benefits; do not invent claims.",
    "Verify and add compatibility details if applicable.",
    "Verify and add dimensions details if applicable."
  ],
  "quality_score": 0.79,
  "confidence": 0.9,
  "risk_level": "low"
}
```

Full schema additionally includes missing_attributes, recommended_keywords,
category_consistency and an explanatory reason. The full actual response and a combined
plan are recorded in [listing-demo.json](../docs/examples/listing-demo.json).
The correct recommendation preserves known content where additional facts are absent.

API/orchestration do not persist recommendations. An explicit application persistence
service follows previous agents: stage a pending Recommendation row of type listing,
flush, and leave commit/rollback to the caller. It never changes Product fields.
Saved read APIs and frontend support typed listing payloads. Repeated explicit saves
can create separate records, as with prior agents; repeated endpoint calls create none.

## Orchestration integration

Existing goal routes retain their behavior. New deterministic routes:

| Goal | Agents |
| --- | --- |
| improve product listings | Listing |
| improve catalog quality | Listing |
| improve product discoverability | Listing |
| optimize product information | Listing |
| improve product performance | Pricing + Promotion + Listing |
| improve listings while protecting inventory | Restock + Listing |

Explicit merchant/product scope is validated before reads. No default all-agent route
was introduced. Promotion continues to enforce its internal Restock protection even
when the broader performance route does not select a standalone Restock result.

Quality below configured 0.60 plus a proposed promotion produces a synergy explaining
listing improvement before or alongside discounts, followed by reassessing demand.
Poor listing plus pricing reduction explains reviewing completeness before relying on
lower prices. These relationships do not claim causal proof. Listing/Restock adds no
conflict: text improvement and replenishment can coexist. Listing steps remain low
priority; critical inventory and existing pricing urgency retain precedence. Existing
stable tie ordering places listing before other same-product low-priority proposals.
Original agent outputs, partial-failure reporting and approval-required plans remain.

## Frontend and demo

ListingCard shows quality, risk/confidence, category alignment, issues, suggestions,
missing details to verify, search terms, and Current vs Recommended title/description.
Product drawer adds Run Listing Analysis, enabled without inventory. Recommendations
adds listing filters/session/saved results. AI Manager offers listing goals, coordinated
steps and original listing cards. Agent Activity shows Pricing, Restock, Promotion,
Listing, and Master Orchestrator all Active in Recommendation Only mode.
No Apply Listing, Publish Listing, Update Product or commerce-write controls exist.

Run the application using README's existing backend/frontend setup. In Products open
Wireless Noise-Canceling Headphones and run Listing Analysis. The agent preserves its
known title/description, identifies missing detail, and requests verification without
inventing connectivity, compatibility or dimensions.

The recorded combined demo uses Organic Cotton Everyday Tee (SKU-AP-003, price 26,
225 available units) in a separate seeded in-memory SQLite store. Product ages were
set to 60 days to allow Promotion's observation-window rule, and this product's
description was removed only in that isolated copy to simulate an incomplete listing.
Names, category, SKU, prices, inventory and available features use existing seed facts;
production data was untouched.

For “improve product performance,” Listing returned quality 48%, confidence 70%, medium
risk and the safe proposed description “Organic Cotton Everyday Tee. Category: Apparel.
SKU: SKU-AP-003.” Pricing held 26; Promotion proposed 10% at 23.40. The plan explains
listing/promotion synergy, orders listing review first among low-priority proposals,
and requires approval without execution. Overall risk medium, confidence 70%, no conflicts.

## Verification

```bash
cd backend
venv/bin/python -m pytest tests/test_listing.py -q
venv/bin/python -m pytest tests/test_listing_orchestration.py -q
venv/bin/python -m pytest -q
cd ../frontend
npm test -- --run
npm run build
```

Listing tests: 36 passed. Orchestrator tests: 84 passed (68 prior + 16 listing integration).
Total backend: 292 passed. Frontend: 39 passed. TypeScript/Vite build passed. No lint
script is configured. Existing Phase 1–7 regressions remain passing.

Tests cover weak/good listings, missing descriptions/categories, deterministic scores,
confidence/risk, attribute requests, HTML cleanup, preserved negations, no invented
features, long-content safety, schema/policy bounds, invalid source data, merchant
ownership, sanitized store failures, no autoflush, unchanged products, pending saves
and rollback. Orchestration tests cover routing, inventory-independent listing reads,
synergies, no false restock conflicts, partial failures and ungrounded output rejection.
Frontend tests cover comparisons/cards, missing description, analysis requests/errors,
listing without inventory, session/filter behavior, AI Manager and active-agent UI.

Chrome verified real API loading and product analysis, current/recommended rendering,
combined plan/synergy, session recommendations and five active agents. Recommendation
layouts at 1024/768/390 pixels had no page overflow. Desktop/mobile screenshots were
visually inspected; no unexpected console errors or failed HTTP requests. Browser
verification used isolated SQLite; PostgreSQL mutation was not performed.

## Safety, limitations and Phase 9 readiness

No listing is published. No product title is changed. No product description is changed.
No external commerce write is executed. No approval or action execution is implemented.

Recommendations rely only on available source text. Category/attribute heuristics are
small English-language presence checks, not a taxonomy, truth checker or applicability
classifier. Generic/minimal descriptions may still need merchant-supplied information.
No marketplace-specific SEO ranking, conversion prediction, LLM rewriting or automatic
publication. Session history remains memory-only; authentication is still future work.

All four specialist contracts, safe advisory APIs, coordination and reusable UI cards
are ready for a later guarded-action phase. Phase 9 has not been implemented.
