# PHASE 03 — PRICING AGENT

## Objective

Build the Pricing Agent.

## Inputs

product
price
cost
inventory
sales velocity
historical sales

## Responsibilities

Detect:

high demand
low inventory
slow sales
pricing opportunities

## Output

Structured PricingRecommendation.

Fields:

product_id
current_price
recommended_price
reason
confidence
risk_level

## Rules

Never recommend below cost.

Never exceed configured maximum price increase.

Never exceed configured maximum price decrease.

## Testing

Test:

high demand
low demand
low inventory
high inventory
boundary prices
below-cost protection

## Important

Agent produces recommendations only.

No automatic price changes.