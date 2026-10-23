import { useState } from "react";
import { workflows, type ChatMessage } from "../services/workflows";
import { shopMoney, type ShoppingCart, type ShopProduct } from "../services/commerce";

export function BuyerAssistant({ token, budget, cart, onCart, onProducts }: { token: string; budget: number; cart: ShoppingCart | null; onCart: (cart: ShoppingCart) => void; onProducts: (products: ShopProduct[]) => void }) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [saved, setSaved] = useState<ShoppingCart[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function load() {
    setOpen(true); setBusy(true); setError("");
    try { const [history, carts] = await Promise.all([workflows.conversation(token), workflows.carts(token)]); setMessages(history.messages); setSaved(carts); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to load conversation."); }
    finally { setBusy(false); }
  }
  return <section className="buyer-chat"><button className="buyer-primary" disabled={!token || busy} onClick={() => open ? setOpen(false) : void load()}>{open ? "Close shopping assistant" : "Chat with CartPilot · saved carts"}</button>{open && <><h2>Your shopping assistant</h2><p>Try “add a mouse”, “find cheaper options”, or “what is my refund status?”. Financial actions require a separate confirmation.</p>{error && <p role="alert">{error}</p>}<div className="buyer-chat-log" role="log" aria-label="Shopping conversation">{messages.map((item, index) => <article className={item.role === "user" ? "chat-user" : "chat-assistant"} key={index}><strong>{item.role === "user" ? "You" : "CartPilot"}</strong><p>{item.text}</p></article>)}</div><form onSubmit={event => { event.preventDefault(); if (!message.trim()) return; setBusy(true); setError(""); workflows.chat(token, message, budget, cart?.id).then(result => { setMessages(result.history); if (result.products.length) onProducts(result.products); if (result.cart) onCart(result.cart); setMessage(""); }).catch(reason => setError(reason instanceof Error ? reason.message : "Unable to send message.")).finally(() => setBusy(false)); }}><label>Message<input aria-label="Message to shopping assistant" maxLength={1000} value={message} onChange={event => setMessage(event.target.value)} disabled={busy} required /></label><button className="buyer-primary" disabled={busy || !budget}>Send message</button><button type="button" disabled={busy} onClick={() => { setBusy(true); workflows.clearConversation(token).then(() => setMessages([])).catch(reason => setError(String(reason))).finally(() => setBusy(false)); }}>Clear conversation</button></form><details><summary>Saved carts in this shopping session ({saved.length})</summary>{saved.map(value => <button key={value.id} disabled={busy} onClick={() => onCart(value)}>{value.status.replace(/_/g, " ")} · {shopMoney(value.total_paise)} · {value.id.slice(0, 8)}</button>)}</details></>}</section>;
}
