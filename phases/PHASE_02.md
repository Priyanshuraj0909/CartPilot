# PHASE 02 — DATA LAYER

## Objective

Create the database and mock e-commerce data.

## Models

Merchant
Product
Inventory
Order
OrderItem
PriceHistory
AgentRun
Recommendation
Action
Approval
AuditLog

## Product

Fields:

id
sku
name
description
category
price
cost
status
created_at
updated_at

## Inventory

Fields:

product_id
quantity
reserved_quantity
reorder_point
reorder_quantity
updated_at

## Order

Fields:

id
merchant_id
status
total
created_at

## Requirements

Create:

SQLAlchemy models
Pydantic schemas
database migrations
seed script

Generate at least:

20 products
100 orders
realistic inventory levels

## Tests

Test:

product creation
inventory retrieval
order retrieval
sales aggregation