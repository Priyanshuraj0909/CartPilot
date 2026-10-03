import { AccountGate } from "./components/AccountGate";
import { useEffect, useState } from "react";
import { StoreProvider, useStore } from "./hooks/useStore";
import { Shell } from "./components/layout/Shell";
import { ProductDrawer } from "./components/ProductDrawer";
import { EmptyState } from "./components/common";
import { Dashboard } from "./pages/Dashboard";
import { Products } from "./pages/Products";
import { InventoryPage } from "./pages/Inventory";
import { AIManager } from "./pages/AIManager";
import { Recommendations } from "./pages/Recommendations";
import { AgentActivity } from "./pages/AgentActivity";
import { Approvals } from "./pages/Approvals";
import { ActionHistory } from "./pages/ActionHistory";
import { Integrations } from "./pages/Integrations";
function Workspace() {
  const [path, setPath] = useState(window.location.pathname === "/" ? "/dashboard" : window.location.pathname);
  const [selected, setSelected] = useState<number | null>(null);
  const store = useStore();
  useEffect(() => { const update = () => { setPath(window.location.pathname === "/" ? "/dashboard" : window.location.pathname); setSelected(null); }; window.addEventListener("popstate", update); return () => window.removeEventListener("popstate", update); }, []);
  useEffect(() => setSelected(null), [store.merchantId]);
  function navigate(next: string) { if (next !== path) window.history.pushState({}, "", next); setPath(next); setSelected(null); window.scrollTo?.(0, 0); }
  const product = store.catalog?.products.find(item => item.id === selected);
  return <Shell path={path} navigate={navigate}><div key={store.merchantId ?? "no-store"}>{path === "/integrations" ? <Integrations /> : path === "/dashboard" ? <Dashboard onDetails={setSelected} navigate={navigate} /> : path === "/products" ? <Products onDetails={setSelected} /> : path === "/inventory" ? <InventoryPage onDetails={setSelected} /> : path === "/ai-manager" ? <AIManager /> : path === "/recommendations" ? <Recommendations /> : path === "/agent-activity" ? <AgentActivity /> : path === "/approvals" ? <Approvals /> : path === "/action-history" ? <ActionHistory /> : <EmptyState>Page not found. <button className="text-btn" onClick={() => navigate("/dashboard")}>Return to Dashboard</button></EmptyState>}{product && <ProductDrawer product={product} close={() => setSelected(null)} />}</div></Shell>;
}
export function App() { return <AccountGate><StoreProvider><Workspace /></StoreProvider></AccountGate>; }
export default App;
