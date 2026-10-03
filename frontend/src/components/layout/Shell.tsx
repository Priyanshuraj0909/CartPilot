import { LayoutDashboard, Package, Layers, Sparkles, ClipboardList, Activity, Compass, RefreshCw, CheckCircle, History } from "lucide-react";
import type { ReactNode } from "react";
import { useStore } from "../../hooks/useStore";
import { HealthBadge } from "../HealthBadge";
import { currency } from "../../services/format";
const navigation = [
  ["/dashboard", "Dashboard", LayoutDashboard], ["/products", "Products", Package], ["/inventory", "Inventory", Layers],
  ["/ai-manager", "AI Manager", Sparkles], ["/recommendations", "Recommendations", ClipboardList], ["/agent-activity", "Agent Activity", Activity], ["/approvals", "Approvals", CheckCircle], ["/action-history", "Action History", History], ["/integrations", "Integrations", RefreshCw],
] as const;
export function Shell({ path, navigate, children }: { path: string; navigate: (path: string) => void; children: ReactNode }) {
  const store = useStore();
  return <div className="app-shell"><aside className="sidebar"><a href="/dashboard" className="brand" onClick={event => { event.preventDefault(); navigate("/dashboard"); }}><span className="brand-mark"><Compass size={25} /></span><span>CartPilot<small>AI MANAGER</small></span></a>
    <p className="nav-label">WORKSPACE</p><nav aria-label="Main navigation">{navigation.map(([url, label, Icon]) => <a key={url} href={url} aria-current={path === url ? "page" : undefined} onClick={event => { if (!event.metaKey && !event.ctrlKey) { event.preventDefault(); navigate(url); } }}><Icon size={18} />{label}</a>)}</nav>
    <div className="sidebar-note"><span className="status-dot" /> You approve each action<p>Sense → Decide → Review</p><small>You stay in control of every decision.</small></div></aside>
    <div className="workspace"><header className="topbar"><div><span className="workspace-label">Your workspace</span><select aria-label="Merchant" value={store.merchantId ?? ""} onChange={event => store.setMerchantId(Number(event.target.value))}>{!store.merchants.length && <option value="">No store available</option>}{store.merchants.map(merchant => <option key={merchant.id} value={merchant.id}>{merchant.store_name}</option>)}</select></div><div className="header-tools"><span className="currency-label">Display currency: {currency}</span><HealthBadge health={store.health} /><button className="icon-btn" aria-label="Refresh store data" onClick={store.refresh}><RefreshCw size={17} /></button></div></header>
    <main>{children}</main><footer>CartPilot · Merchant decision support <span>Local/Simulated · Not synchronized to Shopify.</span></footer></div></div>;
}
