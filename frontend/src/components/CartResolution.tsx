import { useRef, useState } from "react";
import { workflows, type ResolutionState } from "../services/workflows";
import { commerce, parseBudget, shopMoney, type ShoppingCart, type ShopProduct } from "../services/commerce";

export function CartResolution({ token, cart, onCart }: { token: string; cart: ShoppingCart; onCart: (cart: ShoppingCart) => void }) {
  const [state, setState] = useState<ResolutionState | null>(null);
  const [suggestions, setSuggestions] = useState<{ upsells: ShopProduct[]; substitutes: ShopProduct[] } | null>(null);
  const [amount, setAmount] = useState("");
  const [offer, setOffer] = useState<Awaited<ReturnType<typeof workflows.offer>> | null>(null);
  const [editing, setEditing] = useState(false);
  const [quantities, setQuantities] = useState<Record<number, number>>(Object.fromEntries(cart.items.map(line => [line.product_id, line.quantity])));
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const keys = useRef<Record<string, string>>({});
  async function load() {
    setBusy(true); setError("");
    try { const next = await workflows.resolution(token, cart.id); setState(next); setAmount(String(next.refundable_paise / 100)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to load cart actions."); }
    finally { setBusy(false); }
  }
  async function execute(action: string) {
    if (action !== "reconcile" && !confirmed) return;
    setBusy(true); setError("");
    try {
      const value = action === "refund" ? parseBudget(amount) : undefined;
      if (value === null) throw new Error("Enter a valid refund amount.");
      const identity = `${cart.id}:${action}:${value || 0}`;
      const key = keys.current[identity] || (keys.current[identity] = crypto.randomUUID());
      const result = await workflows.resolve(token, cart.id, action, key, value);
      if ("details" in result && result.details.recovered_cart_id) onCart(await commerce.refreshCart(token, result.details.recovered_cart_id));
      else onCart(await commerce.refreshCart(token, cart.id));
      setState(await workflows.resolution(token, cart.id)); setConfirmed(false);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Operation unavailable. Reconcile before retrying."); }
    finally { setBusy(false); }
  }
  return <section className="cart-resolution"><button className="text-btn" disabled={busy} onClick={() => void load()}>Recovery, cancellation & refunds</button>{error && <p role="alert">{error}</p>}{state && <><p>Refundable balance: {shopMoney(state.refundable_paise)}</p><p>Refunds and payments here are simulations or provider tests.</p><label><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} /> I reviewed and confirm the selected operation</label>{state.can_refund && <label>Refund amount (INR)<input aria-label="Refund amount in INR" value={amount} onChange={event => setAmount(event.target.value)} /></label>}<div className="resolution-buttons">{[["cancel", state.can_cancel], ["recover", state.can_recover], ["refund", state.can_refund], ["return_review", state.can_return_review]].map(([action, allowed]) => allowed && <button key={String(action)} disabled={busy || !confirmed} onClick={() => void execute(String(action))}>Confirm {String(action).replace(/_/g, " ")}</button>)}<button disabled={busy} onClick={() => void execute("reconcile")}>Reconcile provider status</button></div>{state.pending_operation && <p>A provider result is pending. Reconcile before requesting another operation.</p>}{state.operations.map(operation => <p key={operation.id}>{operation.action.replace(/_/g, " ")}: {operation.status.replace(/_/g, " ")} · {shopMoney(operation.amount_paise)}</p>)}</>}{["draft", "approved"].includes(cart.status) && <><button className="text-btn" disabled={busy} onClick={() => { setBusy(true); workflows.suggestions(token, cart.id).then(setSuggestions).catch(reason => setError(String(reason))).finally(() => setBusy(false)); }}>Show upsells and substitutes</button>{suggestions && <>{suggestions.upsells.map(product => <button key={product.id} disabled={busy} onClick={() => { setBusy(true); workflows.addItem(token, cart.id, product.id).then(onCart).catch(reason => setError(String(reason))).finally(() => setBusy(false)); }}>Add {product.name} · {shopMoney(product.price_paise)} (new draft)</button>)}<h4>Substitutes</h4>{suggestions.substitutes.map(product => <button key={product.id} disabled={busy} onClick={() => { setBusy(true); workflows.replaceItem(token, cart.id, cart.items[0].product_id, product.id).then(onCart).catch(reason => setError(String(reason))).finally(() => setBusy(false)); }}>Replace {cart.items[0].name} with {product.name} · {shopMoney(product.price_paise)} (new draft)</button>)}{!suggestions.substitutes.length && <p>No matching substitutes available.</p>}</>}</>}<button className="text-btn" disabled={busy} onClick={() => { setBusy(true); workflows.offer(token, cart.id).then(setOffer).catch(reason => setError(String(reason))).finally(() => setBusy(false)); }}>Check recovery offer</button>{offer && <><p>{offer.reason}</p>{offer.eligible && <><p>Save {shopMoney(offer.saving_paise || 0)} · New total {shopMoney(offer.total_paise || 0)}</p><button disabled={busy} onClick={() => { setBusy(true); const identity = `${cart.id}:offer`; const key = keys.current[identity] || (keys.current[identity] = crypto.randomUUID()); workflows.acceptOffer(token, cart.id, key).then(onCart).catch(reason => setError(String(reason))).finally(() => setBusy(false)); }}>Accept recovery offer as new draft</button></>}</>}{["draft", "approved"].includes(cart.status) && <><button disabled={busy} onClick={() => setEditing(!editing)}>Edit cart quantities</button>{editing && <form onSubmit={event => { event.preventDefault(); setBusy(true); const items = cart.items.map(line => ({ product_id: line.product_id, quantity: quantities[line.product_id] || 0 })).filter(line => line.quantity > 0); workflows.revise(token, cart.id, cart.budget_paise, items).then(onCart).catch(reason => setError(String(reason))).finally(() => setBusy(false)); }}>{cart.items.map(line => <label key={line.product_id}>{line.name}<input aria-label={`Edit quantity for ${line.name}`} type="number" min={0} max={20} value={quantities[line.product_id]} onChange={event => setQuantities({ ...quantities, [line.product_id]: Number(event.target.value) })} /></label>)}<small>Set zero to remove an item. Saving resets approval.</small><button disabled={busy}>Save revised draft</button></form>}</>}</section>;
}
