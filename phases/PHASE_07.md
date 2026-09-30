# PHASE 07 — PROMOTION AGENT

## Objective

Detect promotion opportunities.

## Signals

sales velocity
inventory
product age
margin
recent revenue
historical sales

## Outputs

PromotionRecommendation

product_id
promotion_type
discount_percentage
reason
expected_effect
risk_level

## Safety

Never exceed merchant discount policy.

Never recommend discount below minimum margin.

Recommendation only.