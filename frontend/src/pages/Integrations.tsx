import { useEffect, useState } from "react";
import { useStore } from "../hooks/useStore";
import { useTask } from "../hooks/useTask";
import { api, SHOPIFY_PRODUCTION_MESSAGE } from "../services/api";
import { formatDate } from "../services/format";
import { Badge, ErrorAlert, Loading } from "../components/common";
import type { ShopifyStatus, ShopifySync } from "../types";

export function Integrations() {
  const store = useStore();
  const connection = useTask<ShopifyStatus>(store.merchantId ?? 0);
  const sync = useTask<ShopifySync>(store.merchantId ?? 0);
  const [last, setLast] = useState<ShopifySync | null>(null);
  useEffect(() => {
    setLast(null);
    if (store.merchantId) void connection.run(signal => api.getShopifyStatus(store.merchantId!, signal), result => setLast(result.last_sync));
  }, [store.merchantId]);
  const result = sync.data ?? last;
  const productionBlocked = connection.error === SHOPIFY_PRODUCTION_MESSAGE;
  return <><p className="eyebrow">STORE CONNECTIONS</p><h1>Integrations</h1><p className="muted">Import store data for analysis. Shopify remains the source of truth.</p>
    <section className="panel">{store.error && <ErrorAlert message={`Connection failed. ${store.error}`} />}<h2>Shopify</h2><Badge>READ ONLY</Badge>
      {connection.loading && <Loading text="Testing Shopify connection…" />}
      {productionBlocked ? <p role="status">{SHOPIFY_PRODUCTION_MESSAGE}</p>
        : connection.error && <ErrorAlert message={`Connection failed. ${connection.error}`} />}
      {connection.data && <><h3>{connection.data.connected ? "Connected" : connection.data.configured ? "Connection failed" : "Not configured"}</h3><p>{connection.data.message}</p><p>Store: {connection.data.store ?? "Unavailable"}</p><p>API version: {connection.data.api_version} · Currency: {connection.data.currency ?? "Unavailable"}</p></>}
      <p>Shopify credentials are managed privately in the backend environment. The access token is never shown here. Local/demo data works independently.</p>
      <div className="button-row"><button className="btn secondary" disabled={productionBlocked || !store.merchantId || connection.loading || sync.loading} onClick={() => connection.run(signal => api.getShopifyStatus(store.merchantId!, signal), value => setLast(value.last_sync))}>Test Connection</button>
      <button className="btn" disabled={!connection.data?.connected || connection.loading || sync.loading} onClick={() => sync.run(signal => api.syncShopify(store.merchantId!, signal), value => { setLast(value); store.refresh(); })}>Sync Now</button></div>
      {sync.loading && <Loading text="Synchronizing Shopify data..." />}{sync.error && <ErrorAlert message={sync.error} />}
      {result ? <div aria-live="polite"><h3>Synchronization {result.status}</h3><p>Last Sync: {formatDate(result.completed_at ?? result.started_at)}</p><p>Products: {result.products_created + result.products_updated} · Inventory records: {result.inventory_updated} · Orders: {result.orders_created + result.orders_updated} · Skipped orders: {result.orders_skipped} · Errors: {result.errors.length}</p>{result.errors.map((error, index) => <p key={index} role="alert">{error.stage}: {error.message}</p>)}{result.warnings.map(message => <p key={message}>{message}</p>)}</div> : <p>No synchronization recorded.</p>}
      <p className="muted">Local/Simulated actions are not synchronized to Shopify. Sync imports Shopify values into the cache.</p>
    </section></>;
}
