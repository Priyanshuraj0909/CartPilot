import { buyerRequest, type ShoppingCart, type ShopProduct } from "./commerce";
import { request } from "./api";

export interface ChatMessage { role: string; text: string }
export interface ChatResponse { message: string; products: ShopProduct[]; cart: ShoppingCart | null; actions: string[]; trace: { step: string; reason: string }[]; history: ChatMessage[]; intent_source: string }
export interface Operation { id: string; action: string; status: string; amount_paise: number; provider_id: string | null; details: { recovered_cart_id?: string; message?: string; simulation?: boolean } }
export interface ResolutionState { cart_id: string; status: string; refundable_paise: number; refunded_paise: number; pending_operation: boolean; can_refund: boolean; can_cancel: boolean; can_recover: boolean; can_return_review?: boolean; operations: Operation[] }
export interface Compatibility { category_a: string; category_b: string; weight: number; reason: string }
export interface GrowthRule { id: string; kind: "feature_category" | "recovery_offer" | "seasonal_feature"; category: string; enabled: boolean; discount_percent: number; season?: "summer" | "monsoon" | "winter" | "transition" | null; campaign_name?: string; starts_at?: number | null; ends_at?: number | null }
export interface Rules { compatibility: Compatibility[]; growth_rules: GrowthRule[]; scheduler_enabled: boolean; interval_seconds: number }
export interface AuditDashboard { carts: { cart: ShoppingCart; valid: boolean; operations?: Operation[]; events: { sequence: number; event: string; created_at: number; digest: string }[] }[] }
export const workflows = {
  conversation: (token: string) => buyerRequest<{ messages: ChatMessage[]; context: Record<string, unknown> }>("/conversation", token),
  clearConversation: (token: string) => buyerRequest<{ cleared: boolean }>("/conversation", token, undefined, "DELETE"),
  chat: (token: string, message: string, budget_paise: number, cart_id?: string) => buyerRequest<ChatResponse>("/chat", token, { message, budget_paise, cart_id }),
  carts: (token: string) => buyerRequest<ShoppingCart[]>("/carts", token),
  resolution: (token: string, cartId: string) => buyerRequest<ResolutionState>(`/carts/${cartId}/resolution`, token),
  resolve: (token: string, cartId: string, action: string, request_key: string, amount_paise?: number) => buyerRequest<Operation | ResolutionState>(`/carts/${cartId}/resolution`, token, { action, request_key, amount_paise, confirm: true }),
  redeem: (token: string, handoff: string) => buyerRequest<ShoppingCart>("/handoff/redeem", token, { token: handoff }),
  suggestions: (token: string, cartId: string) => buyerRequest<{ upsells: ShopProduct[]; substitutes: ShopProduct[] }>(`/carts/${cartId}/suggestions`, token),
  addItem: (token: string, cartId: string, product_id: number) => buyerRequest<ShoppingCart>(`/carts/${cartId}/add-item`, token, { product_id, quantity: 1, confirm: true, source: "upsell" }),
  replaceItem: (token: string, cartId: string, original_product_id: number, product_id: number) => buyerRequest<ShoppingCart>(`/carts/${cartId}/replace-item`, token, { original_product_id, product_id, quantity: 1, confirm: true }),
  revise: (token: string, cartId: string, budget_paise: number, items: { product_id: number; quantity: number }[]) => buyerRequest<ShoppingCart>(`/carts/${cartId}/revise`, token, { budget_paise, items }),
  offer: (token: string, cartId: string) => buyerRequest<{ eligible: boolean; reason: string; saving_paise?: number; total_paise?: number }>(`/carts/${cartId}/offer`, token),
  acceptOffer: (token: string, cartId: string, request_key: string) => buyerRequest<ShoppingCart>(`/carts/${cartId}/offer`, token, { confirm: true, request_key }),
  rules: () => request<Rules>("/api/v1/commerce/merchant/rules"),
  saveRules: (rules: Rules) => request<Rules>("/api/v1/commerce/merchant/rules", undefined, rules, "PUT"),
  generate: () => request<{ compatibility: Compatibility[]; source: string }>("/api/v1/commerce/merchant/compatibility/generate", undefined, { confirm: true }),
  cycle: () => request<{ executed: { product_id: number; kind: string }[]; note: string }>("/api/v1/commerce/merchant/growth-cycle", undefined, { confirm: true }),
  preview: (query: string, budget_paise: number) => request<{ baseline: ShopProduct[]; hybrid: ShopProduct[]; interpretation: string }>("/api/v1/commerce/merchant/ranking-preview", undefined, { query, budget_paise }),
  context: () => request<{ season: string; note: string; events?: { name: string; category: string; starts_at: number; ends_at: number | null }[]; weather: { temperature_c: number; precipitation_mm: number } | null }>("/api/v1/commerce/merchant/context"),
  lift: () => request<{ pairs: { product_a: number; product_b: number; lift: number; orders_together: number }[]; interpretation: string }>("/api/v1/commerce/merchant/lift"),
  audit: () => request<AuditDashboard>("/api/v1/commerce/merchant/audit"),
  demo: () => request<{ imported: number }>("/api/v1/commerce/merchant/catalog/demo", undefined, { confirm: true }),
  importApi: (source: "dummyjson" | "configured") => request<{ imported: number; skipped: number }>("/api/v1/commerce/merchant/catalog/provider", undefined, { confirm: true, source }),
  reviewReturn: (id: string, decision: string) => request<Operation>(`/api/v1/commerce/merchant/returns/${id}/review`, undefined, { confirm: true, decision }),
  ownerRecover: (cartId: string, request_key: string) => request<{ review_path?: string }>(`/api/v1/commerce/merchant/carts/${cartId}/resolution`, undefined, { action: "recover", request_key, confirm: true }),
  attribution: () => request<{ recorded_upsell_acceptances: number; recorded_recovery_acceptances: number; test_paid_upsell_value_paise: number; interpretation: string }>("/api/v1/commerce/merchant/attribution"),
  archive: () => request<{ archived: number }>("/api/v1/commerce/merchant/catalog/archive", undefined, { confirm: true }),
};
