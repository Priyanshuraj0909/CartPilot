import { useStore } from "../hooks/useStore";
import { Badge, EmptyState, PageTitle } from "../components/common";
import { formatDate } from "../services/format";
export function AgentActivity() {
  const store = useStore();
  const agents = [
    { name: "Pricing Agent", kind: "pricing", purpose: "Evaluates price, cost, demand, and inventory within configured limits." },
    { name: "Restock Agent", kind: "restock", purpose: "Estimates inventory coverage and proposes bounded replenishment quantities." },
    { name: "Promotion Agent", kind: "promotion", purpose: "Detects excess inventory and weak demand; proposes discounts within margin and stockout guardrails." },
    { name: "Listing Agent", kind: "listing", purpose: "Reviews listing quality and recommends factual content improvements using known product information." },
    { name: "Master Orchestrator", kind: "orchestrator", purpose: "Coordinates agent proposals, priorities, and inventory conflicts." },
  ];
  return <><PageTitle title="Agent Activity" description="See what each specialist does and review analyses from this session." /><div className="inventory-grid">{agents.map(agent => { const runs = store.analyses.filter(item => item.kind === agent.kind); return <article className="panel agent-card" key={agent.kind}><Badge tone="healthy">Active</Badge><h2>{agent.name}</h2><p>{agent.purpose}</p><div className="agent-mode">Recommendation Only</div><dl><dt>Analyses this session</dt><dd>{runs.length}</dd><dt>Last analysis</dt><dd>{runs[0] ? formatDate(runs[0].created_at) : "Not run this session"}</dd></dl></article>; })}</div><h2 className="section-title">Session activity</h2><p className="muted">Browser-session activity only. Historical AgentRun records are not exposed by this UI.</p>{store.analyses.length ? <div className="panel">{store.analyses.map((item, index) => <div className="activity-row" key={`${item.created_at}-${index}`}><span className="status-dot" /><div><strong>{item.kind === "orchestrator" ? "Master Orchestrator" : `${item.kind} agent`}</strong><small>{item.kind === "orchestrator" ? item.data.summary : item.data.reason}</small></div><span>{formatDate(item.created_at)}</span><Badge>{item.kind === "orchestrator" && !item.data.complete ? "Partial result" : "Result returned"}</Badge></div>)}</div> : <EmptyState>No analyses this session. Start in Products or AI Manager.</EmptyState>}</>;
}
