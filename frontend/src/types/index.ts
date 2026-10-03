export interface HealthStatus {
  status: "ok" | "degraded" | "error" | "loading";
  app?: string;
  environment?: string;
  database?: string;
  redis?: string;
  version?: string;
}

export interface MetricCardData {
  title: string;
  value: string;
  change?: string;
  changeType?: "positive" | "negative" | "neutral";
  caption?: string;
}

export type Risk = "low" | "medium" | "high";
export type AgentName = "pricing" | "restock" | "promotion" | "listing";
export type Money = number | string;
export interface Merchant { id: number; name: string; store_name: string }
export interface Inventory { quantity: number; reserved_quantity: number; unavailable_quantity?: number; available_quantity: number; reorder_point: number; reorder_quantity: number }
export interface Product {
  id: number; merchant_id: number; name: string; sku: string; category: string; description: string | null;
  selling_price: Money; cost_price: Money | null; source?: "local" | "shopify"; status: string; inventory: Inventory | null;
  sales_velocity: number; recent_units: number; days_remaining: number | null; stockout_risk: boolean | null;
  inventory_status: "Healthy" | "Low Stock" | "Critical" | "Out of Stock" | "Missing" | "Invalid";
  price_history: { id: number; old_price: Money; new_price: Money; changed_at: string; reason: string | null }[];
}
export interface Catalog {
  products: Product[]; total_products: number; low_stock_products: number; potential_stockouts: number;
  available_units: number; recent_orders: number; revenue: Money; lookback_days: number; as_of: string; has_more: boolean;
}
export interface PricingRecommendation {
  product_id: number; current_price: number; recommended_price: number; cost_price: number;
  price_change_percent: number; sales_velocity: number; inventory_quantity: number;
  reason: string; confidence: number; risk_level: Risk;
}
export interface RestockRecommendation {
  product_id: number; current_inventory: number; available_inventory: number; sales_velocity: number;
  estimated_daily_sales: number; estimated_days_remaining: number | null; recommended_quantity: number;
  reason: string; confidence: number; risk_level: Risk; reorder_point: number; lead_time_days: number;
  safety_stock: number; projected_demand_during_lead_time: number; stockout_risk: boolean;
}
export interface Conflict { type: string; product_id: number; severity: Risk; message: string; resolution: string }
export interface AgentResult {
  agent_name: AgentName; product_id: number; success: boolean;
  recommendation: PricingRecommendation | RestockRecommendation | PromotionRecommendation | ListingRecommendation | null; risk_level: Risk; confidence: number;
  error: { code: string; message: string } | null;
}
export interface PlanRecommendation {
  agent: AgentName; product_id: number; priority: "critical" | "high" | "medium" | "low";
  action: "restock" | "review_inventory" | "review_price_change" | "hold_price" | "monitor_inventory" | "review_promotion" | "no_promotion" | "review_listing";
  recommended_price: number | null; recommended_quantity: number | null; deferred: boolean; coordination_reason: string;
}
export interface ActionPlan {
  merchant_id: number; goal: string; summary: string; selected_agents: AgentName[]; selection_reason: string;
  recommendations: PlanRecommendation[]; agent_results: AgentResult[]; conflicts: Conflict[];
  relationships: { type: string; product_id: number; message: string }[];
  overall_risk: Risk; overall_confidence: number; approval_required: boolean; complete: boolean; created_at: string;
  products_analyzed?: number;
  opportunity_summary?: { pricing_opportunities: number[]; restock_risks: number[]; promotion_opportunities: number[]; listing_issues: number[] };
  opportunities?: { product_id: number; product_name: string; selected_agents: AgentName[]; selection_reasons: Partial<Record<AgentName, string>> }[];
  prioritized_actions?: PrioritizedAction[]; blocked_actions?: PrioritizedAction[]; omitted_actions?: PrioritizedAction[];
  recommendation_relationships?: RecommendationRelationship[]; warnings?: string[]; scope_has_more?: boolean;
}
export const goalStrategies = [{ value: "maximize_revenue", label: "Maximize Revenue" }, { value: "avoid_stockouts", label: "Avoid Stockouts" }, { value: "reduce_excess_inventory", label: "Reduce Excess Inventory" }, { value: "improve_product_performance", label: "Improve Product Performance" }, { value: "improve_catalog_quality", label: "Improve Catalog Quality" }, { value: "balanced_growth", label: "Balanced Growth" }] as const;
export const goals = ["maximize_revenue", "avoid_stockouts", "reduce_excess_inventory", "improve_product_performance", "improve_catalog_quality", "balanced_growth", "optimize pricing", "increase revenue", "avoid stockouts", "protect inventory",
  "increase revenue while avoiding stockouts", "improve revenue while maintaining inventory health", "move slow inventory", "increase sell-through", "reduce excess inventory", "improve revenue from slow-moving products", "increase revenue while maintaining healthy inventory", "improve product listings", "improve catalog quality", "improve product discoverability", "optimize product information", "improve product performance", "improve listings while protecting inventory"] as const;
export interface OrchestrationRequest { merchant_id: number; goal: typeof goals[number]; product_ids?: number[] | null; limit?: number }
export interface SavedRecommendation {
  id: number; product_id: number | null; product_name: string | null; agent: string; title: string;
  description: string | null; confidence: number; risk_level: Risk | null; status: string; created_at: string;
  payload: PricingRecommendation | RestockRecommendation | PromotionRecommendation | ListingRecommendation | null;
}
export type Analysis = { created_at: string; merchant_id: number } & (
  { kind: "pricing"; data: PricingRecommendation } | { kind: "restock"; data: RestockRecommendation } |
  { kind: "promotion"; data: PromotionRecommendation } |
  { kind: "listing"; data: ListingRecommendation } |
  { kind: "orchestrator"; data: ActionPlan });

export interface PromotionRecommendation {
  product_id: number; current_price: number; cost_price: number; promotion_recommended: boolean;
  promotion_type: "none" | "discount"; discount_percentage: number; promotional_price: number;
  reason: string; confidence: number; risk_level: Risk; available_inventory: number;
  sales_velocity: number; sales_trend: "increasing" | "stable" | "declining" | "insufficient_data";
  gross_margin_percent: number; retained_margin_percent: number; days_of_inventory: number | null;
  recent_units: number; previous_units: number; expected_effect: string;
}

export interface ListingRecommendation {
  product_id: number; current_title: string; recommended_title: string;
  current_description: string | null; recommended_description: string;
  issues: string[]; suggestions: string[]; missing_attributes: string[];
  quality_score: number; recommended_keywords: string[];
  category_consistency: "consistent" | "inconsistent" | "unverified" | "missing";
  confidence: number; risk_level: Risk; reason: string;
}

export type RecommendationValue = PricingRecommendation | RestockRecommendation | PromotionRecommendation | ListingRecommendation;
export type ActionStatus = "pending" | "validated" | "awaiting_approval" | "approved" | "rejected" | "executing" | "executed" | "failed" | "cancelled";
export type ActionPayload = { product_id: number } & (
  { kind: "price_change"; old_price: Money; new_price: Money; expected_cost: Money } |
  { kind: "restock"; quantity: number } |
  { kind: "promotion"; old_price: Money; expected_cost: Money; discount_percentage: Money; promotional_price: Money } |
  { kind: "listing_update"; old_title: string; old_description: string | null; expected_category: string | null; expected_sku: string; new_title: string; new_description: string });
export interface PolicyValidationResult { is_valid: boolean; policy_name: string; violations: string[]; warnings: string[]; requires_approval: true; risk_level: Risk }
export interface GuardedAction {
  id: number; recommendation_id: number; merchant_id: number; product_id: number; product_name: string;
  agent: string; reason: string; action_type: ActionPayload["kind"]; payload: ActionPayload;
  status: ActionStatus; risk_level: Risk; approval_required: true; execution_mode: "local_mutation" | "simulated";
  created_at: string; executed_at: string | null; approved_by: string | null; approval_status: string; comment: string | null;
  policy: PolicyValidationResult; result: { outcome?: string; message?: string; before?: Record<string, unknown>; after?: Record<string, unknown>; violations?: string[]; requested?: Record<string, unknown> } | null;
}
export type ActionCreate = { merchant_id: number } & ({ recommendation_id: number } | { agent: AgentName; recommendation: RecommendationValue });
export interface ActionAudit { id: number; action_id: number; merchant_id: number; event_type: string; message: string; metadata: Record<string, unknown> | null; created_at: string }

export interface PrioritizedAction {
 id: string; rank: number; product_id: number; product_name: string; agent: AgentName;
 action_type: "price_change" | "restock" | "promotion" | "listing_update" | "review_inventory";
 priority: "critical" | "high" | "medium" | "low"; priority_score: number;
 reason: string; confidence: number; risk: Risk; blocked: boolean; blocked_reason: string | null;
 depends_on: string[]; approval_candidate: boolean;
}
export interface RecommendationRelationship {
 product_id: number; agent_a: AgentName; agent_b: AgentName;
 relationship_type: "conflict" | "synergy" | "independent" | "dependency";
 severity: Risk; explanation: string; recommended_resolution: string;
}

export interface ShopifySync { mode: "read_only"; status: "started" | "completed" | "partial" | "failed"; started_at: string; completed_at: string | null; products_created: number; products_updated: number; inventory_updated: number; orders_created: number; orders_updated: number; orders_skipped: number; errors: {stage: string; code: string; message: string}[]; warnings: string[] }
export interface ShopifyStatus { configured: boolean; connected: boolean; mode: "read_only"; store: string | null; currency: string | null; api_version: string; message: string; last_sync: ShopifySync | null }
