# Final screenshot pack

15 actual Chrome screenshots of the built React frontend, captured 3 October 2026.
Synthetic seeded data only; the primary merchant is **Four-product Demo**. Shopify
uses **Shopify Offline Demo** with mocked HTTP and is never presented as live verification.
Default display is USD; numeric demo prices have no stored currency/FX conversion.
No AI-generated UI, console overlays, real tokens or live-store data are included.

| File | Report/PPT caption |
| --- | --- |
| [01_dashboard.png](01_dashboard.png) | Four-product store overview and inventory exposure |
| [02_products.png](02_products.png) | Flagship product catalog, scoped merchant and available stock |
| [03_product_detail.png](03_product_detail.png) | Verified Mouse source facts and physical/reserved/available inventory |
| [04_pricing_agent.png](04_pricing_agent.png) | Bounded 999→1048.95 Mouse price recommendation; analysis only |
| [05_restock_agent.png](05_restock_agent.png) | Mouse coverage/reorder proposal and stockout exposure |
| [06_promotion_agent.png](06_promotion_agent.png) | Speaker retained-margin-protected 10% discount recommendation |
| [07_listing_agent.png](07_listing_agent.png) | Headphones current/proposed factual listing and verification requests |
| [08_ai_manager.png](08_ai_manager.png) | Balanced Growth goal and merchant analysis controls |
| [09_priority_plan.png](09_priority_plan.png) | Full four-item coordinated priority queue (native browser crop) |
| [10_cross_agent_intelligence.png](10_cross_agent_intelligence.png) | Actual inventory/demand conflict and recommended resolution (native browser crop) |
| [11_approval_workflow.png](11_approval_workflow.png) | Human review before execution; local/demo boundary visible |
| [12_execution_confirmation.png](12_execution_confirmation.png) | Separate confirmation, current-state validation and local-only warning |
| [13_audit_history.png](13_audit_history.png) | Persisted execution event and action audit history |
| [14_policy_block.png](14_policy_block.png) | Unsafe 50% proposal rejected by policy; local price does not change |
| [15_shopify_read_only_mock.png](15_shopify_read_only_mock.png) | READ ONLY mocked Shopify import; merchant explicitly labeled Offline Demo |

## Reproduce

Start a **new disposable database** with DEMO_SCRIPT.md's helper, build/preview on
5174 using backend 8012, and launch an isolated Chrome debugging profile on 9227.
Then from root:

```bash
node scripts/submission_browser.mjs
```

Node 26 was used (native WebSocket). Script refuses a non-loopback frontend or a
backend outside test mode. It runs the workflow, changes only disposable local Mouse
price, submits the blocked fixture, captures all screenshots and writes
`docs/examples/submission-browser.json`. Use a fresh database before another live demo;
do not repeatedly analyze/re-execute the captured database and expect original prices.

Example Chrome command on macOS (separate terminal):

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --no-first-run --no-default-browser-check --remote-debugging-port=9227 --user-data-dir=/tmp/cartpilot-submission-chrome about:blank
```

Use the installed Chrome executable for your OS. A running browser/profile is required;
no browser dependency is added to the product. Captures use viewport, page or element
regions directly through CDP and do not edit application data to manufacture screenshots.
The unsafe fixture uses the existing Action API, not a nonexistent UI proposal editor.
