import type { ShopifyStatus, ShopifySync, GuardedAction, ActionCreate, ActionAudit, ListingRecommendation, PromotionRecommendation, ActionPlan, Catalog, HealthStatus, Merchant, OrchestrationRequest, PricingRecommendation, Product, RestockRecommendation, SavedRecommendation } from "../types";

const base = (import.meta.env.VITE_API_URL || (import.meta.env.PROD ? "" : "http://localhost:8000")).replace(/\/$/, "");
export class ApiError extends Error { constructor(message: string, public status: number) { super(message); } }
async function request<T>(path: string, signal?: AbortSignal, body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${base}${path}`, { signal, ...(body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }) });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError("Unable to reach CartPilot. Check that the backend is running and try again.", 0);
  }
  if (!response.ok) {
    const messages: Record<number, string> = {
      404: "The merchant or product could not be found. Refresh your store data.",
      403: "This product does not belong to the selected merchant.",
      409: "This action changed or is not approved for execution. Refresh the action list.",
      503: "CartPilot could not complete this request. Store data is temporarily unavailable. Please try again.",
      422: "The analysis could not be validated. Check product inventory and your selection.",
    };
    throw new ApiError(messages[response.status] || "CartPilot could not complete this request. Please try again.", response.status);
  }
  try { return await response.json() as T; }
  catch { throw new ApiError("CartPilot returned an unreadable response. Please try again.", response.status); }
}
export const api = {
  getShopifyStatus: (merchantId: number, signal?: AbortSignal) => request<ShopifyStatus>(`/api/v1/integrations/shopify/status?merchant_id=${merchantId}`, signal),
  syncShopify: (merchantId: number, signal?: AbortSignal) => request<ShopifySync>("/api/v1/integrations/shopify/sync", signal, {merchant_id: merchantId}),
  getHealth: (signal?: AbortSignal) => request<HealthStatus>("/api/v1/health/detailed", signal),
  getMerchants: (signal?: AbortSignal) => request<Merchant[]>("/api/v1/merchants", signal),
  getProducts: (id: number, signal?: AbortSignal, offset = 0) => request<Catalog>(`/api/v1/products?merchant_id=${id}&offset=${offset}`, signal),
  getInventory: (id: number, signal?: AbortSignal) => request<Product[]>(`/api/v1/inventory?merchant_id=${id}`, signal),
  getRecommendations: (id: number, signal?: AbortSignal) => request<SavedRecommendation[]>(`/api/v1/recommendations?merchant_id=${id}`, signal),
  getPricingRecommendation: (id: number, merchantId: number, signal?: AbortSignal) => request<PricingRecommendation>("/api/v1/pricing/recommend", signal, { product_id: id, merchant_id: merchantId }),
  getRestockRecommendation: (id: number, merchantId: number, signal?: AbortSignal) => request<RestockRecommendation>("/api/v1/restock/recommend", signal, { product_id: id, merchant_id: merchantId }),
  getPromotionRecommendation: (id: number, merchantId: number, signal?: AbortSignal) => request<PromotionRecommendation>("/api/v1/promotion/recommend", signal, { product_id: id, merchant_id: merchantId }),
  getListingRecommendation: (id: number, merchantId: number, signal?: AbortSignal) => request<ListingRecommendation>("/api/v1/listing/recommend", signal, { product_id: id, merchant_id: merchantId }),
  createAction: (body: ActionCreate, signal?: AbortSignal) => request<GuardedAction>("/api/v1/actions", signal, body),
  getActions: (merchantId: number, signal?: AbortSignal, offset = 0) => request<GuardedAction[]>(`/api/v1/actions?merchant_id=${merchantId}&offset=${offset}`, signal),
  getActionHistory: (merchantId: number, signal?: AbortSignal, offset = 0) => request<ActionAudit[]>(`/api/v1/action-history?merchant_id=${merchantId}&offset=${offset}`, signal),
  reviewAction: (id: number, merchantId: number, approved: boolean, comment: string, signal?: AbortSignal) => request<GuardedAction>(`/api/v1/actions/${id}/${approved ? "approve" : "reject"}`, signal, { merchant_id: merchantId, actor: "development-merchant", comment }),
  executeAction: (id: number, merchantId: number, signal?: AbortSignal) => request<GuardedAction>(`/api/v1/actions/${id}/execute`, signal, { merchant_id: merchantId, actor: "development-merchant", confirm: true }),
  runOrchestrator: (body: OrchestrationRequest, signal?: AbortSignal) => request<ActionPlan>("/api/v1/orchestrate", signal, body),
};
