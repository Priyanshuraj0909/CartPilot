import { useState } from "react";
import type { Product } from "../types";
import { formatCurrency } from "../services/format";
import { Badge, EmptyState } from "./common";
export function ProductTable({ products, onDetails }: { products: Product[]; onDetails: (id: number) => void }) {
  const [search, setSearch] = useState("");
  const rows = products.filter(product => `${product.name} ${product.sku} ${product.category}`.toLowerCase().includes(search.toLowerCase()));
  return <section className="panel table-panel"><div className="table-heading"><h2>Product catalogue <span>{products.length}</span></h2><input className="search" aria-label="Search products" placeholder="Search product, SKU or category…" value={search} onChange={event => setSearch(event.target.value)} /></div><div className="table-scroll"><table><thead><tr><th>Product</th><th>Price / cost</th><th>Available stock</th><th>Sales velocity</th><th>Inventory status</th><th>AI status</th><th>Analysis</th></tr></thead><tbody>{rows.map(product => <tr key={product.id}><td><strong>{product.name}</strong><small>{product.sku} · {product.category}</small></td><td><strong>{formatCurrency(product.selling_price)}</strong><small>Cost {formatCurrency(product.cost_price)}</small></td><td>{product.inventory ? `${product.inventory.available_quantity} units` : "Unavailable"}</td><td>{product.sales_velocity.toFixed(2)}/day</td><td><Badge tone={product.inventory_status}>{product.inventory_status}</Badge></td><td><Badge>Available to analyze</Badge></td><td><button className="text-btn" onClick={() => onDetails(product.id)} aria-label={`Analyze ${product.name}`}>View & analyze →</button></td></tr>)}</tbody></table></div>{!rows.length && <EmptyState>No products match your search.</EmptyState>}</section>;
}
