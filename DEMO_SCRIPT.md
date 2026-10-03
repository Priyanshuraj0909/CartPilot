# CartPilot faculty demo — approximately 7 minutes

Audience: project guide/examiner. Use **Four-product Demo**, Balanced Growth and the
existing safe local workflow. Never depend on internet, Shopify or cloud hosting.
All amounts are stored demo values; default presentation currency is USD, not FX conversion.

## Rehearsal / offline launch

Run from repository root with dependencies already installed:

```bash
cd backend
source venv/bin/activate
# New disposable DB for EVERY fresh rehearsal; never reuse the capture helper's mutated DB.
cartpilot_demo_db=$(mktemp /tmp/cartpilot-final-demo.XXXXXX)
export ENVIRONMENT=test DATABASE_URL="sqlite+aiosqlite:///$cartpilot_demo_db"
export REDIS_URL= CORS_ORIGINS=http://127.0.0.1:5174
export SHOPIFY_STORE_DOMAIN= SHOPIFY_ACCESS_TOKEN=
unset SHOPIFY_MERCHANT_ID
python -m alembic upgrade head
python -m tests.release_demo
```

In another terminal from repository root:

```bash
cd frontend
npm ci --offline
# Use ordinary npm ci if the dependencies are not cached; prepare before going offline.
VITE_API_URL=http://127.0.0.1:8012 npm run build
npm run preview -- --host 127.0.0.1 --port 5174 --strictPort
```

Open http://127.0.0.1:5174/dashboard. Select **Four-product Demo**. Offline demo helper
explicitly seeds the ordinary store, adds the flagship fixture, and mocks Shopify HTTP
using synthetic data. It requires test mode plus disposable SQLite. Preview is only
a local production-artifact check, not a production hosting recommendation.

For ordinary local PostgreSQL (Docker must be installed), instead follow README/setup
and DEPLOYMENT.md: `docker compose up -d postgres redis`, backend migration, explicit
`python -m app.core.seed`, `sh scripts/start.sh`, and frontend `npm run dev` on 5173.
That standard seed is a broader store; the exact flagship fixture is the isolated helper
above. Both keep all actions behind approval. No manual database edits are needed.

If dependencies are missing: Python 3.12 → `python3.12 -m venv venv` → activate →
`pip install -r requirements.txt -c requirements.lock.txt` in backend. Initial dependency
installation can require internet; the prepared demo itself does not. Test local launch
before presentation day, and retain screenshots as a backup if the laptop runtime fails.

## Flagship store

| Product | Actual fixture signal | Demonstrated result |
| --- | --- | --- |
| A — Wireless Mouse | 12 physical, 4 reserved, 8 available; v=5/day; price 999 | Critical restock 67 units, possible +5% price, promotion suppressed |
| B — Bluetooth Speaker Desktop Audio | 120 available; declining sales; cost 850, price 1499 | 10% promotion to 1349.10; competing base-price decrease deferred |
| C — Headphones | 50 physical, very weak sales, missing description | Listing improvement first; weak demand also implies long coverage, so promotion is secondary/blocked pending listing |
| D — Keyboard Desktop USB Wired | 20 available; v=.5/day; factual description | No urgent operational action |

Expected queue: **critical Mouse restock → high Headphones listing → high Speaker
promotion → medium Mouse price review**. Low stock blocks Mouse demand stimulation.
Actual JSON example is in docs/examples/cross-agent-demo.json. Explain blocked work
rather than hiding it. Risk and priority are different: Mouse pricing can be high risk
but medium priority. Exactly four products belong to the selected flagship store;
other merchants exist to test scope and optional mocked Shopify.

## Clicks, narration and purpose

| Time | Click / expected screen | Say / why it matters |
| --- | --- | --- |
| 0:00–0:35 | Dashboard; select Four-product Demo | “Store decisions are fragmented. CartPilot coordinates four specialists above the same data.” Show stock/demand visibility, not measured revenue improvement. |
| 0:35–1:05 | Products; open Wireless Mouse | “Reserved stock is excluded. We have eight available units and five units/day demand.” Source facts explain urgency. |
| 1:05–1:55 | Run Pricing Analysis, then Restock Analysis | “Pricing proposes 999→1048.95, but stock safety takes priority. Restock estimates 1.6 days remaining and 67 units.” Analysis changes nothing. |
| 1:55–2:40 | Speaker → Run Promotion Analysis; Headphones → Run Listing Analysis | “The Speaker supports a guarded 10% discount. For missing listing details, the system requests verification instead of inventing features.” Show current/proposed content. |
| 2:40–3:55 | AI Manager → Balanced Growth → Analyze Store | “Shared context becomes one priority queue. Restock comes first; listing review precedes inappropriate demand remedies.” Show blocked actions and Conflicts, Synergies and Dependencies. |
| 3:55–5:15 | Mouse pricing → Create Action for Review → Approvals → Approve → Execute Approved Action → confirm Execute | “Approval alone does not execute. The executor revalidates current state and then changes only local demo data.” Show the confirmation and 1048.95 outcome. |
| 5:15–5:55 | Prepare blocked example below; Approvals → Refresh actions → failed filter | “A typed proposal outside the 10% policy cannot be approved. Safety does not depend on an agent's confidence.” Show policy violation. |
| 5:55–6:20 | Action History | “Every review/execution has persistent audit evidence.” Show execution_completed and before/after values. |
| 6:20–6:50 | Integrations; select Shopify Offline Demo → Sync Now | “This is explicitly mocked verification, not a live store. READ ONLY queries import variant/stock/order data. Local edits never write back.” |
| 6:50–7:10 | Return to Four-product Demo / architecture slide | “The contribution is explainable coordination with guarded execution. Forecasting, authentication and external writes remain future work.” |

## Unsafe proposal (no database edits)

From root while the isolated demo API is running:

```bash
backend/venv/bin/python scripts/demo_policy_block.py
```

This test-only loopback helper submits a 50% Mouse price proposal through the existing
Action API, confirms `status=failed` and invalid policy, and prints the nonsecret result.
It does not execute a price change. It works before or after the safe action; a repeated
identical proposal is deduplicated. Display the new failed action using Refresh actions.
There is no arbitrary-price proposal editor in the UI, so do not pretend this was entered
through a frontend feature. Disclose the helper as a reproducible safety fixture.

## Optional stale-state explanation

Reliable automated evidence (fresh test fixtures only):

```bash
cd backend
venv/bin/python -m pytest tests/test_actions.py::test_promotion_current_stockout_block tests/test_actions.py::test_stale_price -q
```

The test approves a promotion, changes stock inside its isolated fixture, and proves
execution is blocked; changed price/cost also blocks. Use this evidence during viva
rather than manually editing presentation data. Approved status can remain with a
blocked result; inspect current policy/result, not just the approval label.

## Failure fallback and rehearsal checklist

- Internet/Shopify unavailable: use the four-product data; optional Shopify panel is
  mocked by the helper. If using a real store separately, skip that portion on failure.
- Hosted site unavailable: use the exact loopback launch above; no cloud dependency.
- Runtime unavailable: use the 15 labeled screenshots and JSON evidence; disclose
  prerecorded evidence rather than claiming a live execution.
- [ ] Backend/frontend and fresh disposable DB ready; migration/helper completed.
- [ ] Four-product merchant selected and expected queue rehearsed.
- [ ] Safe action, unsafe helper and audit tested; screenshot/report tabs prepared.
- [ ] Optional Shopify shown as mocked/read-only; no token screens or console clutter.
- [ ] Browser console clean; ports 8012/5174 available; charger/display ready.

Stop old processes before starting a fresh rehearsal. Reset by choosing a new disposable
file and rerunning migrations/helper; never delete a valuable DB or add a public reset API.
