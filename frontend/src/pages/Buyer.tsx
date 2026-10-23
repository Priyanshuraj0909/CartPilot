import { useEffect, useState } from "react";
import { BuyerAssistant } from "../components/BuyerAssistant";
import { CartResolution } from "../components/CartResolution";
import { workflows } from "../services/workflows";
import { ArrowRight, Compass, Search, ShieldCheck, ShoppingBag, Sparkles } from "lucide-react";
import { commerce, parseBudget, shopMoney } from "../services/commerce";
import type { Audit, ShopProduct, ShoppingCart, Storefront } from "../services/commerce";

export function Buyer({ merchantId, standalone = false }: { merchantId: number; standalone?: boolean }) {
  const [store, setStore] = useState<Storefront | null>(null);
  const [products, setProducts] = useState<ShopProduct[]>([]);
  const [token, setToken] = useState("");
  const [query, setQuery] = useState("");
  const [budget, setBudget] = useState("10000");
  const [selected, setSelected] = useState<Record<number, number>>({});
  const [cart, setCart] = useState<ShoppingCart | null>(null);
  const [audit, setAudit] = useState<Audit | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("Tell us what you’re looking for. Every cart stays under your control.");
  const [mode, setMode] = useState("simulation");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let alive = true;
    Promise.all([commerce.store(merchantId), commerce.session(merchantId)]).then(([next, identity]) => {
      if (!alive) return;
      setStore(next); setProducts(next.products); setToken(identity.token); setBudget(String(Math.min(1000000, next.max_spend_paise) / 100));
      const handoff = new URLSearchParams(window.location.hash.slice(1)).get("handoff");
      if (handoff) { window.history.replaceState({}, "", window.location.pathname); workflows.redeem(identity.token, handoff).then(value => { if (alive) setCart(value); }).catch(reason => { if (alive) setError(reason instanceof Error ? reason.message : "Handoff unavailable."); }); }
    }).catch(reason => { if (alive) setError(reason instanceof Error ? reason.message : "Unable to open this store."); }).finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [merchantId]);
  async function run(task: () => Promise<void>) {
    setBusy(true); setError("");
    try { await task(); } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to complete this request."); }
    finally { setBusy(false); }
  }
  function validBudget(): number {
    const amount = parseBudget(budget);
    if (amount === null) throw new Error("Enter a positive budget with at most two decimal places, up to ₹10,00,000.");
    return amount;
  }
  function editSelection(id: number, quantity: number) {
    setSelected(previous => ({ ...previous, [id]: quantity })); setCart(null); setAudit(null);
  }
  async function search(anchor?: number) {
    const result = await commerce.search(token, query.trim() || "Show products", validBudget(), anchor);
    setProducts(result.products); setMessage(`${result.message} · ${["gemini", "openai"].includes(result.intent_source) ? "AI-assisted search" : "Local search"}`);
    if (result.budget_paise !== null) { setBudget(String(result.budget_paise / 100)); setCart(null); setAudit(null); }
  }
  function adoptCart(value: ShoppingCart) {
    setCart(value); setAudit(null); setBudget(String(value.budget_paise / 100));
    setSelected(Object.fromEntries(value.items.map(line => [line.product_id, line.quantity])));
  }
  const selection = Object.entries(selected).filter(([, quantity]) => quantity > 0);
  const content = <div className="buyer-experience">
    <header className="buyer-header"><a href="/dashboard" className="buyer-logo"><Compass size={24} /> CartPilot <span>SHOP</span></a><a href="/dashboard">Merchant workspace <ArrowRight size={16} /></a></header>
    <section className="buyer-hero"><div><span className="buyer-eyebrow"><Sparkles size={15} /> YOUR SHOPPING COPILOT</span><h1>A little guidance.<br /><em>A better cart.</em></h1><p>Discover {store?.store_name || "your store"}. Find the right products, understand each suggestion, and shop within your budget.</p><div className="buyer-trust"><ShieldCheck size={17} /> Server-checked prices · Your approval · Test checkout</div></div><div className="buyer-hero-card"><ShoppingBag size={52} strokeWidth={1} /><span>Thoughtfully picked.<br />Always your choice.</span><small>INR · No live charges</small></div></section>
    {loading && <p role="status">Opening your shopping session…</p>}
    {error && <div className="buyer-error" role="alert">{error} {!token && !loading && <button onClick={() => window.location.reload()}>Try again</button>}</div>}
    {store && <><form className="buyer-search" onSubmit={event => { event.preventDefault(); void run(() => search()); }}><label><span>What are you looking for?</span><div><Search size={19} /><input aria-label="Shopping request" maxLength={1000} placeholder="Try “wireless headphones under ₹3,000”" value={query} onChange={event => setQuery(event.target.value)} disabled={busy} /></div></label><label className="buyer-budget"><span>Budget (INR)</span><input aria-label="Budget in INR" inputMode="decimal" value={budget} onChange={event => { setBudget(event.target.value); setCart(null); setAudit(null); }} disabled={busy} /></label><button className="buyer-primary" disabled={busy || !token}>Find my picks <ArrowRight size={17} /></button></form>
    <BuyerAssistant token={token} budget={parseBudget(budget) || 0} cart={cart} onCart={adoptCart} onProducts={setProducts} /><p className="buyer-response" role="status">{busy ? "Checking your request…" : message}</p>
    <div className="buyer-layout"><section><div className="buyer-section-title"><h2>Your next good find</h2><span>{products.length} products {store.truncated && "· bounded catalog preview"}</span></div><div className="buyer-products">{products.map((product, index) => <article className="buyer-product" key={product.id}><div className={`buyer-product-art art-${index % 4}`}><ShoppingBag size={58} strokeWidth={1} /><span>{product.category}</span></div><div className="buyer-product-info"><span className="buyer-eyebrow">{product.category}</span><h3>{product.name}</h3><p>{product.description || "Ask the merchant for additional product details."}</p><strong>{shopMoney(product.price_paise)}</strong><small>{product.available > 0 ? `${product.available} available` : "Out of stock"}</small>{product.reasons && <ul className="buyer-reasons">{product.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul>}<label className="buyer-quantity">Quantity<select aria-label={`Quantity for ${product.name}`} value={selected[product.id] || 0} disabled={busy || product.available < 1} onChange={event => editSelection(product.id, Number(event.target.value))}>{Array.from({ length: Math.min(20, product.available) + 1 }, (_, quantity) => <option key={quantity} value={quantity}>{quantity === 0 ? "Not selected" : quantity}</option>)}</select></label><button className="text-btn" disabled={busy} onClick={() => void run(() => search(product.id))}>Find related products</button></div></article>)}</div>{!products.length && <p className="buyer-empty">No matches within this budget. Try another search.</p>}</section>
    <aside className="buyer-cart"><div className="buyer-section-title"><h2>Your bag</h2><ShoppingBag size={20} /></div><p>{selection.length} selected products</p>{selection.length === 0 && <p className="buyer-empty">Good finds belong here. Choose a quantity to get started.</p>}<button className="buyer-primary" disabled={busy || selection.length === 0} onClick={() => void run(async () => { const next = await commerce.cart(token, validBudget(), selection.map(([id, quantity]) => ({ product_id: Number(id), quantity }))); setCart(next); setAudit(await commerce.audit(token, next.id)); })}>Review server-priced cart</button>
    {cart && <div className="buyer-cart-detail"><span className="buyer-status">{cart.status.replace(/_/g, " ")}</span>{cart.items.map(line => <div className="buyer-cart-line" key={line.product_id}><span>{line.name} × {line.quantity}</span><strong>{shopMoney(line.subtotal_paise)}</strong></div>)}<div className="buyer-total"><span>Total</span><strong>{shopMoney(cart.total_paise)}</strong></div><small>Expires {new Date(cart.expires_at * 1000).toLocaleTimeString()} · Stock is checked, not reserved.</small>{cart.status === "draft" && <button className="buyer-primary" disabled={busy} onClick={() => void run(async () => { setCart(await commerce.approve(token, cart.id)); setAudit(await commerce.audit(token, cart.id)); })}>Approve this cart</button>}{cart.status === "approved" && <><label>Checkout mode<select aria-label="Checkout mode" value={mode} disabled={busy} onChange={event => setMode(event.target.value)}>{store.checkout_modes.map(value => <option key={value} value={value}>{value === "simulation" ? "Offline simulation" : "Razorpay test payment"}</option>)}</select></label><button className="buyer-primary" disabled={busy} onClick={() => void run(async () => { setCart(await commerce.checkout(token, cart.id, mode)); setAudit(await commerce.audit(token, cart.id)); })}>Confirm {mode === "simulation" ? "simulation" : "test checkout"}</button></>}{cart.checkout_url && <a className="buyer-primary" href={cart.checkout_url} target="_blank" rel="noopener noreferrer">Open Razorpay test checkout <ArrowRight size={16} /></a>}{cart.status === "simulated" && <p>Simulation recorded. No payment was taken and no order was placed.</p>}<button className="text-btn" disabled={busy} onClick={() => void run(async () => { setCart(await commerce.refreshCart(token, cart.id)); setAudit(await commerce.audit(token, cart.id)); })}>Refresh cart and payment status</button><small>Cart reference: {cart.id}</small></div>}
    {cart && <CartResolution key={cart.id + cart.status} token={token} cart={cart} onCart={adoptCart} />}{audit && <details className="buyer-audit"><summary>{audit.valid ? "✓ Audit chain verified" : "Audit verification failed"}</summary><ol>{audit.events.map(event => <li key={event.sequence}><strong>{event.event.replace(/_/g, " ")}</strong><code>{event.digest.slice(0, 16)}…</code></li>)}</ol><small>Hash-linked application history; not an externally anchored ledger.</small></details>}<div className="buyer-note"><ShieldCheck size={18} /><p>You approve the cart before a separate checkout confirmation. All payment flows are tests.</p></div></aside></div></>}
  </div>;
  return standalone ? <main>{content}</main> : content;
}
