import { ArrowUpRight, Package, AlertTriangle, ShoppingCart, DollarSign, Sparkles } from "lucide-react";
import { useStore } from "../hooks/useStore";
import { MetricCard } from "../components/MetricCard";
import { ErrorAlert, Loading, PageTitle } from "../components/common";
import { ProductTable } from "../components/ProductTable";
import { formatCurrency } from "../services/format";
export function Dashboard({ onDetails, navigate }: { onDetails: (id: number) => void; navigate: (path: string) => void }) {
  const store = useStore(), data = store.catalog;
  const metrics: [string, string | number | undefined, string, typeof Package][] = [
      ["Total Products", data?.total_products, "In this merchant's catalogue", Package],
      ["Low Stock", data?.low_stock_products, "Includes critical and out of stock", AlertTriangle],
      ["Potential Stockouts", data?.potential_stockouts, "Forecast through supplier lead time", AlertTriangle],
      ["Orders", data?.recent_orders, `Non-cancelled · last ${data?.lookback_days ?? 14} days`, ShoppingCart],
      ["Revenue", data ? formatCurrency(data.revenue) : undefined, "Order revenue · same lookback", DollarSign],
      ["AI Recommendations", data && !store.savedLoading && !store.savedError ? store.saved.length : undefined, "Saved proposals · session results below", Sparkles],
    ];
  return <><PageTitle title="Storefront overview" description="Your AI Manager for Intelligent E-Commerce Operations" /><section className="hero"><div><span className="hero-tag">SENSE → DECIDE → RECOMMEND</span><h2>Good decisions start<br />with a clear view.</h2><p>Understand demand, protect inventory, and review your next move.</p><button className="btn" onClick={() => navigate("/ai-manager")}>Open AI Manager <ArrowUpRight size={16} /></button></div><div className="hero-map"><div><span>01</span> Sense your store</div><div><span>02</span> Coordinate recommendations</div><div><span>03</span> You decide what happens next</div><small>Recommendation only · No automatic execution</small></div></section>
    <section className="panel" aria-labelledby="merchant-workspace-title">
      <h2 id="merchant-workspace-title">Your merchant workspace</h2>
      <p className="muted">Start by adding products, import sales to see recorded revenue, then run the AI Manager. New accounts have their own empty store.</p>
      <div className="workspace-shortcuts">
        <button className="btn" onClick={() => navigate("/store-management")}>Add or edit products</button>
        <button className="btn" onClick={() => navigate("/sales")}>Import sales & view insights</button>
        <button className="btn" onClick={() => navigate("/notifications")}>View stock notifications</button>
      </div>
      {data?.total_products === 0 && <p>Add your first product to populate inventory metrics and generate product recommendations.</p>}
    </section>
    {store.loading && <Loading />}{store.error && <ErrorAlert message={store.error} retry={store.refresh} />}
    <div className="metrics">{metrics.map(([title, value, caption, Icon]) => <MetricCard key={title} title={title} value={store.loading ? "…" : value === undefined ? "—" : String(value)} caption={caption} icon={<Icon size={18} />} />)}</div>
    {data && <><section className="panel"><div className="section-heading"><div><h2>Inventory health</h2><p className="muted">Available inventory accounts for reserved stock.</p></div><span className="badge">{data.products.length} products loaded</span></div><div className="inventory-health">{["Healthy", "Low Stock", "Critical", "Out of Stock", "Missing", "Invalid"].map(status => { const count = data.products.filter(product => product.inventory_status === status).length; return <div key={status}><span>{status}</span><strong>{count}</strong><div className="health-track"><span className={status === "Healthy" ? "green" : status === "Low Stock" ? "amber" : "red"} style={{ width: `${data.products.length ? count / data.products.length * 100 : 0}%` }} /></div></div>; })}</div></section><ProductTable products={data.products.slice(0, 6)} onDetails={onDetails} /><button className="text-btn" onClick={() => navigate("/products")}>View all products →</button></>}
    <div className="diagnostics"><span>Backend: {store.health.status === "ok" || store.health.status === "degraded" ? "Reachable" : "Unavailable"}</span><span>Database: {store.health.database || "Unknown"}</span><span>Redis: {store.health.redis || "Unknown"}</span></div></>;
}
