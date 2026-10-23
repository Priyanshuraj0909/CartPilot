import { request } from "./api";

export interface ShopProduct { id: number; name: string; description: string; category: string; price_paise: number; available: number; reasons?: string[] }
export interface Storefront { store_name: string; currency: string; products: ShopProduct[]; truncated: boolean; max_spend_paise: number; checkout_modes: string[] }
export interface CartLine { product_id: number; name: string; quantity: number; unit_price_paise: number; subtotal_paise: number }
export interface ShoppingCart { id: string; status: string; budget_paise: number; total_paise: number; items: CartLine[]; expires_at: number; checkout_url: string | null }
export interface SearchResult { products: ShopProduct[]; message: string; intent_source: string; budget_paise: number | null; truncated: boolean }
export interface Audit { valid: boolean; events: { sequence: number; event: string; payload: Record<string, unknown>; digest: string; previous_hash: string; created_at: number }[] }
export interface CommercePolicy { published: boolean; max_spend_paise: number; blocked_categories: string[]; boosted_product_ids: number[] }
export interface Growth { counts: Record<string, number>; test_paid_value_paise: number; real_revenue_paise: number; recovery: { cart_id: string; total_paise: number; advice: string; expires_at: number }[]; recommendation_method: string; limitations: string }
const base = (import.meta.env.VITE_API_URL || (import.meta.env.PROD ? "" : "http://localhost:8000")).replace(/\/$/, "");
const pendingShopperSessions = new Map<number, Promise<{ token: string; expires_at: number }>>();
const messages: Record<number, string> = { 401: "Your session expired. Start a new shopping session or sign in to preview a private store.", 404: "This store, product or cart is unavailable.", 409: "The cart changed, expired or needs approval. Build a fresh cart if its stock or prices changed.", 422: "Check your budget, quantities and store category restrictions.", 429: "Too many requests. Please wait a minute.", 503: "Checkout or store data is temporarily unavailable. If checkout was requested, review its status before trying again." };
export async function buyerRequest<T>(path: string, token?: string, body?: unknown, method?: string): Promise<T> {
  const account = sessionStorage.getItem("cartpilot-token");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 30000);
  try {
    const response = await fetch(`${base}/api/v1/commerce${path}`, { signal: controller.signal, headers: {
      ...(account ? { Authorization: `Bearer ${account}` } : {}), ...(token ? { "X-CartPilot-Buyer": token } : {}),
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    }, ...(method ? { method } : {}), ...(body === undefined ? {} : { method: method || "POST", body: JSON.stringify(body) }) });
    if (!response.ok) throw new Error(messages[response.status] || "CartPilot could not complete this request.");
    return await response.json() as T;
  } catch (error) {
    if (error instanceof TypeError || (error instanceof DOMException && error.name === "AbortError")) throw new Error("Unable to reach CartPilot. If checkout was requested, check its status before retrying.");
    throw error;
  } finally { clearTimeout(timer); }
}
export const commerce = {
  store: (id: number) => buyerRequest<Storefront>(`/storefront/${id}`),
  session: async (id: number) => {
    const key = `cartpilot-shopper-${id}`;
    try {
      const stored: unknown = JSON.parse(sessionStorage.getItem(key) || "null");
      if (stored && typeof stored === "object" && "token" in stored && "expires_at" in stored && typeof stored.token === "string" && typeof stored.expires_at === "number" && stored.expires_at * 1000 > Date.now()) return { token: stored.token, expires_at: stored.expires_at };
    } catch { sessionStorage.removeItem(key); }
    const existing = pendingShopperSessions.get(id);
    if (existing) return existing;
    const pending = buyerRequest<{ token: string; expires_at: number }>("/sessions", undefined, { merchant_id: id })
      .then(identity => { sessionStorage.setItem(key, JSON.stringify(identity)); return identity; })
      .finally(() => pendingShopperSessions.delete(id));
    pendingShopperSessions.set(id, pending);
    return pending;
  },
  search: (token: string, query: string, budget_paise: number, anchor_product_id?: number) => buyerRequest<SearchResult>("/search", token, { query, budget_paise, anchor_product_id }),
  cart: (token: string, budget_paise: number, items: { product_id: number; quantity: number }[]) => buyerRequest<ShoppingCart>("/carts", token, { budget_paise, items }),
  approve: (token: string, id: string) => buyerRequest<ShoppingCart>(`/carts/${id}/approve`, token, { confirm: true }),
  checkout: (token: string, id: string, mode: string) => buyerRequest<ShoppingCart>(`/carts/${id}/checkout`, token, { confirm: true, mode }),
  refreshCart: (token: string, id: string) => buyerRequest<ShoppingCart>(`/carts/${id}`, token),
  audit: (token: string, id: string) => buyerRequest<Audit>(`/carts/${id}/audit`, token),
  policy: () => request<CommercePolicy>("/api/v1/commerce/policy"),
  savePolicy: (policy: CommercePolicy) => request<CommercePolicy>("/api/v1/commerce/policy", undefined, policy, "PUT"),
  growth: () => request<Growth>("/api/v1/commerce/growth"),
  importCatalog: (csv_text: string) => request<{ imported: number }>("/api/v1/commerce/catalog/import", undefined, { csv_text }),
  train: () => request<{ orders: number; products: number }>("/api/v1/commerce/models/train", undefined, { confirm: true }),
  index: () => request<{ indexed: number; remaining: number }>("/api/v1/commerce/models/index", undefined, { confirm: true }),
};
export const shopMoney = (paise: number) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" }).format(paise / 100);
export function parseBudget(value: string): number | null {
  if (!/^\d+(\.\d{1,2})?$/.test(value)) return null;
  const paise = Math.round(Number(value) * 100);
  return Number.isSafeInteger(paise) && paise >= 1 && paise <= 100000000 ? paise : null;
}
