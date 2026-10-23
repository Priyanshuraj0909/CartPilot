# Margin analysis workspace

The merchant workspace now uses a responsive enterprise navigation shell and exposes
`/margin-analysis` as the default signed-in landing view. The existing dashboard and
all commerce, catalog, agent, approval and integration routes remain available.

The page calculates current gross margin as `(selling price - cost) / selling price`
from the active merchant's catalog. It compares up to four products, draws at most six
recorded price-history observations, shows available inventory, supports product search,
prints the view and exports the selected rows as CSV. Missing, negative or non-finite
cost/price inputs produce no margin. Storewide recorded revenue is clearly labeled and
is not attributed to selected products.

The trend is descriptive. It does not forecast demand, estimate elasticity or claim a
price change caused a business result. The existing analysis, approval and separate
confirmation workflow remains authoritative for operational changes.

## Local verification

```bash
cd frontend
npm run test:run
npm run build
```

No charting or UI dependency was added; the chart uses accessible native SVG and the
existing React, TypeScript and Lucide stack.
