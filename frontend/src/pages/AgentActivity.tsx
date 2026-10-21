import { useEffect, useRef, useState } from "react";
import { useStore } from "../hooks/useStore";
import { Badge, EmptyState, ErrorAlert, Loading, PageTitle } from "../components/common";
import { formatDate } from "../services/format";
import { api } from "../services/api";
import type { AgentRun } from "../types";
export function AgentActivity() {
  const store = useStore();
  const [history, setHistory] = useState<{ merchantId: number; rows: AgentRun[] } | null>(null);
  const [loading, setLoading] = useState(false), [error, setError] = useState("");
  const [revision, setRevision] = useState(0), [more, setMore] = useState(false);
  const active = useRef<AbortController | null>(null);
  const rows = history?.merchantId === store.merchantId ? history.rows : [];
  async function loadHistory(merchantId: number, offset = 0) {
    active.current?.abort();
    const controller = new AbortController(); active.current = controller;
    setLoading(true); setError("");
    try {
      const data = await api.getAgentRuns(merchantId, controller.signal, offset);
      if (!controller.signal.aborted) {
        setHistory(current => ({ merchantId, rows: offset && current?.merchantId === merchantId ? [...current.rows, ...data] : data }));
        setMore(data.length === 50);
      }
    } catch (cause) {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "Unable to load activity.");
    } finally { if (!controller.signal.aborted) setLoading(false); }
  }
  useEffect(() => {
    setHistory(null); setMore(false); setError(""); setLoading(false);
    if (store.merchantId) void loadHistory(store.merchantId);
    return () => active.current?.abort();
  }, [store.merchantId, revision]);
  const agents = [
    { name: "Pricing Agent", kind: "pricing", purpose: "Evaluates price, cost, demand, and inventory within configured limits." },
    { name: "Restock Agent", kind: "restock", purpose: "Estimates inventory coverage and proposes bounded replenishment quantities." },
    { name: "Promotion Agent", kind: "promotion", purpose: "Detects excess inventory and weak demand; proposes discounts within margin and stockout guardrails." },
    { name: "Listing Agent", kind: "listing", purpose: "Reviews listing quality and recommends factual content improvements using known product information." },
    { name: "Master Orchestrator", kind: "orchestrator", purpose: "Coordinates agent proposals, priorities, and inventory conflicts." },
  ];
  return <><PageTitle title="Agent Activity" description="Review saved AI Manager activity and specialist analyses from this session." />
    {store.error && <ErrorAlert message={store.error} />}
    <h2 className="section-title">Saved AI Manager activity</h2>
    <p className="muted">Plan summaries remain available after signing in again. Individual specialist analyses below are kept for this browser session.</p>
    <button className="btn secondary" disabled={loading || !store.merchantId} onClick={() => setRevision(value => value + 1)}>Refresh activity</button>
    {loading && <Loading text="Loading saved activity…" />}
    {error && <ErrorAlert message={error} retry={() => setRevision(value => value + 1)} />}
    {!loading && !error && store.merchantId && !rows.length && <EmptyState>No saved plans for this merchant. Run AI Manager to begin.</EmptyState>}
    {rows.length > 0 && <div className="panel">{rows.map(run => <div className="activity-row" key={run.id}><span className="status-dot" /><div><strong>{run.input_summary?.goal.replace(/_/g, " ") || "AI Manager plan"}</strong><small>{run.output_summary?.summary || "Plan summary unavailable."}</small><small>{run.output_summary?.products_analyzed ?? 0} products · {run.output_summary?.failed_analyses ?? 0} failed analyses</small></div><span>{formatDate(run.started_at)}</span><Badge tone={run.output_summary?.complete === false || run.status === "failed" ? "medium" : "healthy"}>{run.status === "failed" ? "Failed" : run.output_summary?.complete === false ? "Partial result" : "Completed"}</Badge></div>)}</div>}
    {more && rows.length > 0 && <button className="btn secondary" disabled={loading} onClick={() => { if (store.merchantId) void loadHistory(store.merchantId, rows.length); }}>Load more activity</button>}
    <div className="inventory-grid">{agents.map(agent => { const runs = store.analyses.filter(item => item.kind === agent.kind); return <article className="panel agent-card" key={agent.kind}><Badge tone="healthy">Active</Badge><h2>{agent.name}</h2><p>{agent.purpose}</p><div className="agent-mode">Recommendation Only</div><dl><dt>Analyses this session</dt><dd>{runs.length}</dd><dt>Last analysis</dt><dd>{runs[0] ? formatDate(runs[0].created_at) : "Not run this session"}</dd></dl></article>; })}</div><h2 className="section-title">Session activity</h2>{store.analyses.length ? <div className="panel">{store.analyses.map((item, index) => <div className="activity-row" key={`${item.created_at}-${index}`}><span className="status-dot" /><div><strong>{item.kind === "orchestrator" ? "Master Orchestrator" : `${item.kind} agent`}</strong><small>{item.kind === "orchestrator" ? item.data.summary : item.data.reason}</small></div><span>{formatDate(item.created_at)}</span><Badge>{item.kind === "orchestrator" && !item.data.complete ? "Partial result" : "Result returned"}</Badge></div>)}</div> : <EmptyState>No analyses this session. Start in Products or AI Manager.</EmptyState>}</>;
}
