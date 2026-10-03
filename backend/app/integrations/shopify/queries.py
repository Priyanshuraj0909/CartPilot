"""Closed GraphQL query registry. HTTP POST carries reads, never mutations."""
from enum import StrEnum
class Query(StrEnum):
    SHOP='shop'
    VARIANTS='variants'
    INVENTORY='inventory'
    INVENTORY_NO_COST='inventory_no_cost'
    ORDERS='orders'
    ORDER_LINES='order_lines'

PAGE_INFO='pageInfo { hasNextPage endCursor }'
LINE_FIELDS='id quantity currentQuantity variant { id } discountedUnitPriceAfterAllDiscountsSet { shopMoney { amount currencyCode } }'
INVENTORY_FIELDS='id tracked inventoryLevels(first: 100, after: $cursor) { nodes { id isActive location { id isActive } quantities(names: ["available", "on_hand", "committed", "reserved"]) { name quantity } } '+PAGE_INFO+' }'
QUERIES={
 Query.SHOP: 'query CartPilotShop { shop { name myshopifyDomain currencyCode } currentAppInstallation { accessScopes { handle } } }',
 Query.VARIANTS: 'query CartPilotVariants($cursor: String) { productVariants(first: 100, after: $cursor, sortKey: ID) { nodes { id title sku price inventoryItem { id } product { id title description productType status createdAt updatedAt } } '+PAGE_INFO+' } }',
 Query.INVENTORY: 'query CartPilotInventory($id: ID!, $cursor: String) { inventoryItem(id: $id) { unitCost { amount currencyCode } '+INVENTORY_FIELDS+' } }',
 Query.INVENTORY_NO_COST: 'query CartPilotInventoryNoCost($id: ID!, $cursor: String) { inventoryItem(id: $id) { '+INVENTORY_FIELDS+' } }',
 Query.ORDERS: 'query CartPilotOrders($cursor: String, $filter: String!) { orders(first: 100, after: $cursor, sortKey: CREATED_AT, query: $filter) { nodes { id name createdAt cancelledAt displayFinancialStatus displayFulfillmentStatus currentTotalPriceSet { shopMoney { amount currencyCode } } lineItems(first: 100) { nodes { '+LINE_FIELDS+' } '+PAGE_INFO+' } } '+PAGE_INFO+' } }',
 Query.ORDER_LINES: 'query CartPilotOrderLines($id: ID!, $cursor: String) { order(id: $id) { id lineItems(first: 100, after: $cursor) { nodes { '+LINE_FIELDS+' } '+PAGE_INFO+' } } }',
}
REQUIRED_SCOPES=frozenset({'read_products','read_inventory','read_orders'})
