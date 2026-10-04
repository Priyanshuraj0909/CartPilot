import { SalesImport } from "./SalesImport";
import { formatCurrency } from "../services/format";
import { useEffect, useState, type FormEvent } from 'react';
import { request } from '../services/api';
import { useStore } from '../hooks/useStore';

type SalesSummary = { total_revenue: string; products: { id: number; name: string; units: number; revenue: string }[] };
type Alert = { product: string; message: string };
export function StoreManagement({ mode = 'products' }: { mode?: 'products' | 'sales' | 'notifications' }) {
  const store = useStore();
  const [id, setId] = useState('');
  const [productSearch, setProductSearch] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [insights, setInsights] = useState<SalesSummary | null>(null);
  const [alerts, setAlerts] = useState<Alert[] | null>(null);
  const authenticated = Boolean(sessionStorage.getItem('cartpilot-token'));
  const product = store.catalog?.products.find(p => String(p.id) === id);
  const query = productSearch.trim().toLowerCase();
  const editableProducts = store.catalog?.products.filter(p => p.source !== 'shopify') ?? [];
  const matchingProducts = editableProducts.filter(p => `${p.name} ${p.sku} ${p.category}`.toLowerCase().includes(query));
  const title = mode === 'products' ? 'Manage your store' : mode === 'sales' ? 'Sales & Insights' : 'Notifications';

  useEffect(() => {
    if (!authenticated || mode === 'products') return;
    const controller = new AbortController();
    setError('');
    if (mode === 'sales') request<SalesSummary>('/api/v1/analytics', controller.signal).then(setInsights).catch(e => { if (!controller.signal.aborted) setError(e.message); });
    else request<{ notifications: Alert[] }>('/api/v1/notifications', controller.signal).then(data => setAlerts(data.notifications)).catch(e => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [authenticated, mode, store.catalog]);

  async function run(operation: () => Promise<unknown>, success: string) {
    setBusy(true); setError(''); setMessage('');
    try { await operation(); setMessage(success); store.refresh(); }
    catch (e) { setError(e instanceof Error ? e.message : 'Operation failed.'); }
    finally { setBusy(false); }
  }
  function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const f = new FormData(e.currentTarget);
    void run(() => request(`/api/v1/products${id ? '/' + id : ''}`, undefined, {
      sku: f.get('sku'), name: f.get('name'), category: f.get('category'), description: f.get('description'),
      cost_price: f.get('cost_price'), selling_price: f.get('selling_price'), quantity: Number(f.get('quantity')),
    }, id ? 'PUT' : 'POST'), id ? 'Product changes saved.' : 'Product added. You can now run its analysis.');
  }
  return <section className="card merchant-tools"><h2>{title}</h2>
    {!authenticated ? <><p>Sign in or create a merchant account to manage your own products, import sales and view alerts.</p><button className="btn" onClick={() => window.dispatchEvent(new Event('cartpilot-open-login'))}>Sign in / Create account</button></> : <>
      {error && <p role="alert" className="management-error">{error}</p>}{message && <p role="status">{message}</p>}
      {mode === 'products' && <><p>Add your first products here, then open AI Manager to analyze your store.</p>
        <div className="catalog-search management-search"><label>Find a product to edit<input type="search" placeholder="Enter product name, SKU or category" value={productSearch} onChange={e => setProductSearch(e.target.value)} /></label>{productSearch && <button className="btn secondary" onClick={() => setProductSearch('')}>Clear product search</button>}<small aria-live="polite">{matchingProducts.length} matching products{store.catalog?.has_more ? ' in the loaded catalogue; load more on Products to search more items.' : ''}</small></div>
        <label>Select a product<select value={id} onChange={e => setId(e.target.value)}><option value="">Add new product</option>{editableProducts.filter(p => matchingProducts.includes(p) || String(p.id) === id).map(p => <option key={p.id} value={p.id}>{p.name}{p.status === 'archived' ? ' (archived)' : ''}</option>)}</select></label>
        <form key={id} className="management-form" onSubmit={save}>
          <label>SKU<input name="sku" required maxLength={100} defaultValue={product?.sku} placeholder="MOUSE-001" /></label>
          <label>Product name<input name="name" required maxLength={255} defaultValue={product?.name} /></label>
          <label>Category<input name="category" required maxLength={100} defaultValue={product?.category} placeholder="Electronics" /></label>
          <label>Cost price<input name="cost_price" type="number" min="0" step="0.01" required defaultValue={product?.cost_price ?? 0} /></label>
          <label>Selling price<input name="selling_price" type="number" min="0.01" step="0.01" required defaultValue={product?.selling_price} /></label>
          <label>Physical stock<input name="quantity" type="number" min="0" step="1" required defaultValue={product?.inventory?.quantity ?? 0} /></label>
          <label className="wide">Description<textarea name="description" maxLength={5000} defaultValue={product?.description || ''} /></label>
          <button className="btn" disabled={busy}>{busy ? 'Saving…' : id ? 'Save changes' : 'Add product'}</button>
        </form>{id && <button className="btn secondary" disabled={busy} onClick={() => { if (window.confirm('Archive this product? Its order history will be retained.')) void run(() => request(`/api/v1/products/${id}`, undefined, {}, 'DELETE'), 'Product archived; history retained.'); }}>Archive product</button>}</>}
      {mode === 'sales' && <><SalesImport products={store.catalog?.products.filter(p => p.source !== 'shopify') ?? []} onImported={store.refresh} />
        {insights ? <><h3>Recorded sales revenue: {formatCurrency(insights.total_revenue)}</h3><p>Ranked by units sold. These are observed sales, not predicted revenue growth.</p>{insights.products.length ? <div className="management-table"><table><thead><tr><th>Product</th><th>Units sold</th><th>Revenue</th></tr></thead><tbody>{insights.products.map(p => <tr key={p.id}><td>{p.name}</td><td>{p.units}</td><td>{formatCurrency(p.revenue)}</td></tr>)}</tbody></table></div> : <p>No recorded sales yet. Upload your sales file to populate this summary.</p>}</> : <p role="status">Loading sales summary…</p>}</>}
      {mode === 'notifications' && <><p>Current stock alerts for your store. Email delivery is not configured.</p>{alerts === null ? <p role="status">Loading alerts…</p> : alerts.length ? <ul>{alerts.map((a, i) => <li key={i}><strong>{a.product}</strong> — {a.message}</li>)}</ul> : <p>No low-stock alerts. Your available stock is above the configured reorder points.</p>}<button className="btn secondary" onClick={store.refresh}>Refresh alerts</button></>}
    </>}
  </section>;
}
