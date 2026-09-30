# PHASE 04 — RESTOCK AGENT

## Objective

Build the Restock Agent.

## Inputs

inventory
sales velocity
historical orders
reorder point
lead time

## Outputs

RestockRecommendation

Fields:

product_id
current_inventory
estimated_daily_sales
estimated_days_remaining
recommended_quantity
reason
confidence
risk_level

## Detection

Identify products likely to stock out.

## Safety

Never recommend negative quantity.

Respect maximum reorder quantity.

## Testing

Test:

healthy inventory
low inventory
high velocity
low velocity
zero sales
stockout scenario