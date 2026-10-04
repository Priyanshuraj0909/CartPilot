import { useState } from "react";
import type { Product } from "../types";
import { formatCurrency } from "../services/format";
import { Badge, EmptyState } from "./common";
export function filterProducts(products: Product[], search: string) {
  const query = search.trim().toLowerCase();
  return products.filter(product => `${product.name} ${product.sku} ${product.category}`.toLowerCase().includes(query));
}
export function ProductSearch({ value, onChange, count, total }: { value: string; onChange: (value: string) => void; count: number; total: number }) {
  return <div className="catalog-search"><label>Search products<input type="search" className="search" placeholder="Enter product name, SKU or category" value={value} onChange={event => onChange(event.target.value)} /></label>{value && <button className="btn secondary" onClick={() => onChange("")}>Clear search</button>}<small role="status">Showing {count} of {total} loaded products</small></div>;
}
export function ProductTable({ products, onDetails, search: externalSearch, hideSearch = false }: { products: Product[]; onDetails: (id: number) => void; search?: string; hideSearch?: boolean }) {
  const [search, setSearch] = useState("");
  const rows = filterProducts(products, externalSearch ?? search);
  return <section className="panel table-panel"><div className="table-heading"><h2>Product catalogue <span>{products.length}</span></h2>{!hideSearch && <ProductSearch value={search} onChange={setSearch} count={rows.length} total={products.length} />}</div><div className="table-scroll"><table><thead><tr><th>Product</th><th>Price / cost</th><th>Available stock</th><th>Sales velocity</th><th>Inventory status</th><th>AI status</th><th>Analysis</th></tr></thead><tbody>{rows.map(product => <tr key={product.id}><td><strong>{product.name}</strong><small>{product.sku} · {product.category}</small></td><td><strong>{formatCurrency(product.selling_price)}</strong><small>Cost {formatCurrency(product.cost_price)}</small></td><td>{product.inventory ? `${product.inventory.available_quantity} units` : "Unavailable"}</td><td>{product.sales_velocity.toFixed(2)}/day</td><td><Badge tone={product.inventory_status}>{product.inventory_status}</Badge></td><td><Badge>Available to analyze</Badge></td><td><button className="text-btn" onClick={() => onDetails(product.id)} aria-label={`Analyze ${product.name}`}>View & analyze →</button></td></tr>)}</tbody></table></div>{!rows.length && <EmptyState>No products match your search.</EmptyState>}</section>;
}
