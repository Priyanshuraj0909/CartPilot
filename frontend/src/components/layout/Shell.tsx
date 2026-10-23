import { Activity, BarChart3, Bell, Bot, CheckCircle, ChevronDown, ClipboardList, Compass, HelpCircle, History, Layers, LayoutDashboard, Menu, Package, RefreshCw, Search, Settings, ShoppingBag, Sparkles, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useStore } from "../../hooks/useStore";
import { HealthBadge } from "../HealthBadge";

const groups = [
  { label: "Workspace", items: [["/dashboard", "Main Dashboard", LayoutDashboard], ["/sales", "Sales & Insights", BarChart3]] },
  { label: "Catalog & operations", items: [["/products", "Products", Package], ["/inventory", "Inventory Controls", Layers], ["/store-management", "Manage Store", Settings]] },
  { label: "Inventory intelligence", items: [["/margin-analysis", "Margin Analysis", BarChart3], ["/recommendations", "Recommendations", ClipboardList], ["/growth", "Growth Console", Sparkles]] },
  { label: "AI operations", items: [["/ai-manager", "AI Manager", Bot], ["/approvals", "Approvals", CheckCircle], ["/agent-activity", "Agent Activity", Activity], ["/action-history", "Action History", History]] },
  { label: "Commerce", items: [["/buyer", "Buyer Storefront", ShoppingBag], ["/integrations", "Integrations", RefreshCw], ["/notifications", "Notifications", Bell]] },
] as const;

export function Shell({ path, navigate, children }: { path: string; navigate: (path: string) => void; children: ReactNode }) {
  const store = useStore(), [menuOpen, setMenuOpen] = useState(false), [navQuery, setNavQuery] = useState("");
  const searchRef = useRef<HTMLInputElement>(null);
  const shownGroups = useMemo(() => groups.map(group => ({ ...group, items: group.items.filter(([, label]) => label.toLowerCase().includes(navQuery.trim().toLowerCase())) })).filter(group => group.items.length), [navQuery]);
  useEffect(() => { const shortcut = (event: KeyboardEvent) => { if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); searchRef.current?.focus(); } }; window.addEventListener("keydown", shortcut); return () => window.removeEventListener("keydown", shortcut); }, []);
  function go(url: string) { navigate(url); setMenuOpen(false); }
  return <div className="app-shell enterprise-shell"><button className="mobile-menu" aria-label={menuOpen ? "Close navigation" : "Open navigation"} onClick={() => setMenuOpen(value => !value)}>{menuOpen ? <X /> : <Menu />}</button><aside className={`sidebar enterprise-sidebar${menuOpen ? " open" : ""}`}><a href="/margin-analysis" className="brand" onClick={event => { event.preventDefault(); go("/margin-analysis"); }}><span className="brand-mark"><Compass size={23} /></span><span>CartPilot<small>COMMERCE INTELLIGENCE</small></span></a>
    <div className="merchant-switch"><small>COMPANY</small><select aria-label="Merchant" value={store.merchantId ?? ""} onChange={event => store.setMerchantId(Number(event.target.value))}>{!store.merchants.length && <option value="">No store available</option>}{store.merchants.map(merchant => <option key={merchant.id} value={merchant.id}>{merchant.store_name}</option>)}</select><ChevronDown size={15} /></div><div className="module-chip"><Layers size={18} /><span><small>WORKSPACE</small>Inventory intelligence</span></div>
    <label className="nav-search"><Search size={16} /><input type="search" ref={searchRef} value={navQuery} onChange={event => setNavQuery(event.target.value)} aria-label="Search navigation" placeholder="Search navigation" /><kbd>⌘K</kbd></label>
    <nav aria-label="Main navigation">{shownGroups.map(group => <details key={group.label} open><summary>{group.label}<ChevronDown size={14} /></summary>{group.items.map(([url, label, Icon]) => <a key={url} href={url} aria-current={path === url ? "page" : undefined} onClick={event => { if (!event.metaKey && !event.ctrlKey) { event.preventDefault(); go(url); } }}><Icon size={17} />{label}</a>)}</details>)}</nav>
    <div className="sidebar-note"><span className="status-dot" /> Human approval enforced<p>Analyze → Review → Confirm</p><small>AI recommendations never directly change prices, inventory, or payments.</small></div></aside>
    <div className="workspace"><header className="topbar enterprise-topbar"><div className="global-search"><Search size={18} /><span>Search CartPilot workspace</span><kbd>⌘K</kbd></div><div className="header-tools"><HealthBadge health={store.health} /><button className="icon-btn" aria-label="Open help" onClick={() => go("/dashboard")}><HelpCircle size={18} /></button><button className="icon-btn" aria-label="Open notifications" onClick={() => go("/notifications")}><Bell size={18} /></button><button className="icon-btn" aria-label="Open settings" onClick={() => go("/growth")}><Settings size={18} /></button><button className="icon-btn" aria-label="Refresh store data" onClick={store.refresh}><RefreshCw size={17} /></button></div></header>
    <main>{children}</main><footer>CartPilot · Explainable commerce intelligence <span>Local/simulated operations · merchant approval required.</span></footer></div>{menuOpen && <button className="nav-scrim" aria-label="Close navigation overlay" onClick={() => setMenuOpen(false)} />}</div>;
}
