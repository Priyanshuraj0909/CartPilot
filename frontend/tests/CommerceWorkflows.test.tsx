import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { BuyerAssistant } from "../src/components/BuyerAssistant";
import { CartResolution } from "../src/components/CartResolution";
import { CommerceStudio } from "../src/components/CommerceStudio";
import { workflows } from "../src/services/workflows";
import { commerce, type ShoppingCart } from "../src/services/commerce";

vi.mock("../src/hooks/useStore", () => ({ useStore: () => ({ refresh: vi.fn(), catalog: { products: [{ id: 1, category: "Electronics", name: "Mouse" }, { id: 2, category: "Home", name: "Bottle" }] } }) }));
const cart: ShoppingCart = { id: "cart-1", status: "simulated", budget_paise: 10000, total_paise: 1000, items: [{ product_id: 1, name: "Mouse", quantity: 1, unit_price_paise: 1000, subtotal_paise: 1000 }], expires_at: 2000000000, checkout_url: null };
const state = { cart_id: cart.id, status: cart.status, refundable_paise: 1000, refunded_paise: 0, pending_operation: false, can_refund: true, can_cancel: false, can_recover: false, operations: [] };
beforeEach(() => {
  sessionStorage.clear();
  vi.spyOn(workflows, "conversation").mockResolvedValue({ messages: [{ role: "assistant", text: "Welcome back" }], context: {} });
  vi.spyOn(workflows, "carts").mockResolvedValue([cart]);
  vi.spyOn(workflows, "resolution").mockResolvedValue(state);
  vi.spyOn(commerce, "refreshCart").mockResolvedValue(cart);
  vi.spyOn(workflows, "rules").mockResolvedValue({ compatibility: [], growth_rules: [], scheduler_enabled: false, interval_seconds: 300 });
});

it("restores conversation and lets the shopper resume a saved cart", async () => {
  const onCart = vi.fn();
  render(<BuyerAssistant token="fixture" budget={10000} cart={null} onCart={onCart} onProducts={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: /Chat with CartPilot/ }));
  await screen.findByText("Welcome back");
  fireEvent.click(screen.getByRole("button", { name: /simulated ·/ }));
  expect(onCart).toHaveBeenCalledWith(cart);
});

it("sends grounded chat and receives a draft without implicit payment", async () => {
  const draft = { ...cart, status: "draft" };
  vi.spyOn(workflows, "chat").mockResolvedValue({ message: "Review your draft", products: [], cart: draft, actions: ["review_cart"], trace: [], history: [{ role: "assistant", text: "Review your draft" }], intent_source: "local" });
  const onCart = vi.fn();
  render(<BuyerAssistant token="fixture" budget={10000} cart={null} onCart={onCart} onProducts={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: /Chat with CartPilot/ }));
  await screen.findByText("Welcome back");
  fireEvent.change(screen.getByLabelText("Message to shopping assistant"), { target: { value: "add a mouse" } });
  fireEvent.click(screen.getByRole("button", { name: "Send message" }));
  await screen.findByText("Review your draft");
  expect(onCart).toHaveBeenCalledWith(draft);
});

it("surfaces chat load failures", async () => {
  vi.mocked(workflows.conversation).mockRejectedValue(new Error("Session expired"));
  render(<BuyerAssistant token="fixture" budget={10000} cart={null} onCart={vi.fn()} onProducts={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: /Chat with CartPilot/ }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Session expired");
});

it("disables sending when the shopper budget is invalid", async () => {
  render(<BuyerAssistant token="fixture" budget={0} cart={null} onCart={vi.fn()} onProducts={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: /Chat with CartPilot/ }));
  await screen.findByText("Welcome back");
  expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
});

it("requires explicit confirmation for refunds", async () => {
  vi.spyOn(workflows, "resolve").mockResolvedValue({ id: "op", action: "refund", status: "succeeded", amount_paise: 1000, provider_id: null, details: { simulation: true } });
  render(<CartResolution token="fixture" cart={cart} onCart={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "Recovery, cancellation & refunds" }));
  const confirm = await screen.findByRole("button", { name: "Confirm refund" });
  expect(confirm).toBeDisabled();
  fireEvent.click(screen.getByRole("checkbox", { name: /I reviewed and confirm/ }));
  fireEvent.click(confirm);
  await waitFor(() => expect(workflows.resolve).toHaveBeenCalledWith("fixture", cart.id, "refund", expect.any(String), 1000));
});

it("rejects zero refund amounts in the UI", async () => {
  vi.spyOn(workflows, "resolve");
  render(<CartResolution token="fixture" cart={cart} onCart={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "Recovery, cancellation & refunds" }));
  await screen.findByRole("button", { name: "Confirm refund" });
  fireEvent.change(screen.getByLabelText("Refund amount in INR"), { target: { value: "0" } });
  fireEvent.click(screen.getByRole("checkbox", { name: /I reviewed and confirm/ }));
  fireEvent.click(screen.getByRole("button", { name: "Confirm refund" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("valid refund amount");
  expect(workflows.resolve).not.toHaveBeenCalled();
});

it("reuses the request key after an uncertain provider failure", async () => {
  vi.spyOn(workflows, "resolve").mockRejectedValue(new Error("Result uncertain; reconcile"));
  render(<CartResolution token="fixture" cart={cart} onCart={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "Recovery, cancellation & refunds" }));
  await screen.findByRole("button", { name: "Confirm refund" });
  fireEvent.click(screen.getByRole("checkbox", { name: /I reviewed and confirm/ }));
  fireEvent.click(screen.getByRole("button", { name: "Confirm refund" }));
  await screen.findByRole("alert");
  fireEvent.click(screen.getByRole("button", { name: "Confirm refund" }));
  await waitFor(() => expect(workflows.resolve).toHaveBeenCalledTimes(2));
  expect(vi.mocked(workflows.resolve).mock.calls[0][3]).toBe(vi.mocked(workflows.resolve).mock.calls[1][3]);
});

it("displays an ineligible recovery offer without an acceptance button", async () => {
  vi.spyOn(workflows, "offer").mockResolvedValue({ eligible: false, reason: "Cost is unknown" });
  render(<CartResolution token="fixture" cart={cart} onCart={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "Check recovery offer" }));
  await screen.findByText("Cost is unknown");
  expect(screen.queryByRole("button", { name: "Accept recovery offer as new draft" })).not.toBeInTheDocument();
});

it("saves a merchant growth rule and explicit scheduler choice", async () => {
  vi.spyOn(workflows, "saveRules").mockImplementation(async value => value);
  render(<CommerceStudio />);
  fireEvent.click(screen.getByRole("button", { name: "Manage growth rules" }));
  await screen.findByRole("button", { name: "Add growth rule" });
  fireEvent.click(screen.getByRole("button", { name: "Add growth rule" }));
  fireEvent.click(screen.getByRole("checkbox", { name: /Enable scheduled ranking/ }));
  fireEvent.click(screen.getByRole("button", { name: "Save growth controls" }));
  await screen.findByText("Growth and compatibility settings saved.");
  expect(workflows.saveRules).toHaveBeenCalledWith(expect.objectContaining({ scheduler_enabled: true, growth_rules: [expect.objectContaining({ category: "Electronics", kind: "feature_category" })] }));
});

it("labels ranking comparison without promising revenue lift", async () => {
  vi.spyOn(workflows, "preview").mockResolvedValue({ baseline: [], hybrid: [], interpretation: "Ranking comparison only; no conversion or revenue lift was measured." });
  render(<CommerceStudio />);
  fireEvent.click(screen.getByRole("button", { name: "Compare baseline and hybrid" }));
  expect(await screen.findByText(/no conversion or revenue lift/)).toBeInTheDocument();
});

it("handles API import failure", async () => {
  vi.spyOn(workflows, "importApi").mockRejectedValue(new Error("Provider unavailable"));
  render(<CommerceStudio />);
  fireEvent.click(screen.getByRole("button", { name: "Import DummyJSON catalog" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Provider unavailable");
});

it("requires separate confirmation before catalog archive", () => {
  render(<CommerceStudio />);
  expect(screen.getByRole("button", { name: "Confirm archive local catalog", hidden: true })).toBeDisabled();
});
