import type { ActionPlan, AgentName, GuardedAction, RecommendationValue } from "../types";
import { useStore } from "../hooks/useStore";
import { useTask } from "../hooks/useTask";
import { api } from "../services/api";
import { ErrorAlert } from "./common";
function hasChange(value: RecommendationValue) {
  if ("recommended_price" in value) return value.recommended_price !== value.current_price;
  if ("recommended_quantity" in value) return value.recommended_quantity > 0;
  if ("promotion_recommended" in value) return value.promotion_recommended;
  return value.current_title !== value.recommended_title || value.current_description !== value.recommended_description;
}
export function CreateAction({ agent, recommendation, savedId, disabled = false }: { agent: AgentName; recommendation: RecommendationValue; savedId?: number; disabled?: boolean }) {
  const store = useStore();
  const task = useTask<GuardedAction>(`${store.merchantId}:${savedId ?? JSON.stringify(recommendation)}`);
  const possible = hasChange(recommendation);
  return <div className="action-creation"><button className="btn secondary" disabled={!store.merchantId || !possible || disabled || task.loading || !!task.data} onClick={() => { if (store.merchantId) task.run(signal => api.createAction(savedId ? { merchant_id: store.merchantId!, recommendation_id: savedId } : { merchant_id: store.merchantId!, agent, recommendation }, signal)); }}>{task.loading ? "Validating action…" : "Create Action for Review"}</button>{!possible && <small>No operational change proposed.</small>}{disabled && possible && <small>Deferred by coordination; resolve the plan restrictions first.</small>}{task.error && <ErrorAlert message={task.error} />}{task.data && <div aria-live="polite"><p>Action #{task.data.id} · {task.data.status.replace(/_/g, " ")}. No execution occurred.</p>{!task.data.policy.is_valid && <ErrorAlert message={task.data.policy.violations.join(" ")} />}<a href="/approvals" onClick={event => { event.preventDefault(); window.history.pushState({}, "", "/approvals"); window.dispatchEvent(new PopStateEvent("popstate")); }}>Open Approvals</a></div>}</div>;
}
export function PlanActions({ plan }: { plan: ActionPlan }) {
  return <section className="panel"><h3>Create selected actions for review</h3><p className="muted">Each proposal passes policy validation and requires separate human approval and execution.</p>{plan.agent_results.filter(result => result.success && result.recommendation).map(result => { const step = plan.recommendations.find(item => item.agent === result.agent_name && item.product_id === result.product_id); return <div className="plan-action-option" key={`${result.agent_name}-${result.product_id}`}><strong>{result.agent_name} · Product {result.product_id}</strong><CreateAction agent={result.agent_name} recommendation={result.recommendation!} disabled={!step || step.deferred || ["hold_price", "no_promotion", "monitor_inventory", "review_inventory"].includes(step.action)} /></div>; })}</section>;
}
