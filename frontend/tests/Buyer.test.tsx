import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Buyer } from "../src/pages/Buyer";
import { commerce, parseBudget } from "../src/services/commerce";
import type { Audit, ShoppingCart, Storefront } from "../src/services/commerce";

const product = { id: 1, name: "Wireless Mouse", description: "Quiet computer mouse", category: "Electronics", price_paise: 10000, available: 25 };
const storefront: Storefront = { store_name: "Demo Shop", currency: "INR", products: [product], truncated: false, max_spend_paise: 1000000, checkout_modes: ["simulation"] };
const cart: ShoppingCart = { id: "cart-fixture", status: "draft", budget_paise: 1000000, total_paise: 10000, items: [{ product_id: 1, name: product.name, quantity: 1, unit_price_paise: 10000, subtotal_paise: 10000 }], expires_at: 2000000000, checkout_url: null };
const audit: Audit = { valid: true, events: [{ sequence: 1, event: "cart_proposed", payload: {}, digest: "1234567890abcdef0000", previous_hash: "0", created_at: 1 }] };

beforeEach(() => {
  vi.spyOn(commerce, "store").mockResolvedValue(storefront);
  vi.spyOn(commerce, "session").mockResolvedValue({ token: "shopper-fixture", expires_at: 2000000000 });
  vi.spyOn(commerce, "search").mockResolvedValue({ products: [product], message: "Choose products", intent_source: "local", budget_paise: 1000000, truncated: false });
  vi.spyOn(commerce, "cart").mockResolvedValue(cart);
  vi.spyOn(commerce, "audit").mockResolvedValue(audit);
  vi.spyOn(commerce, "approve").mockResolvedValue({ ...cart, status: "approved" });
  vi.spyOn(commerce, "checkout").mockResolvedValue({ ...cart, status: "simulated" });
});

describe("Buyer storefront", () => {
  it("requires review, approval and separate checkout confirmation", async () => {
    render(<Buyer merchantId={1} />);
    await screen.findByText("Wireless Mouse");
    fireEvent.change(screen.getByLabelText("Quantity for Wireless Mouse"), { target: { value: "1" } });
    fireEvent.click(screen.getByRole("button", { name: "Review server-priced cart" }));
    await screen.findByRole("button", { name: "Approve this cart" });
    expect(commerce.checkout).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Approve this cart" }));
    await screen.findByRole("button", { name: "Confirm simulation" });
    expect(commerce.checkout).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Confirm simulation" }));
    await screen.findByText("Simulation recorded. No payment was taken and no order was placed.");
    expect(commerce.checkout).toHaveBeenCalledWith("shopper-fixture", "cart-fixture", "simulation");
    expect(screen.getByText("✓ Audit chain verified")).toBeInTheDocument();
  });

  it("blocks an invalid budget before calling search", async () => {
    render(<Buyer merchantId={1} />);
    await screen.findByText("Wireless Mouse");
    fireEvent.change(screen.getByLabelText("Budget in INR"), { target: { value: "0" } });
    fireEvent.click(screen.getByRole("button", { name: "Find my picks" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Enter a positive budget");
    expect(commerce.search).not.toHaveBeenCalled();
  });

  it("clears approval when the selection changes", async () => {
    render(<Buyer merchantId={1} />);
    await screen.findByText("Wireless Mouse");
    fireEvent.change(screen.getByLabelText("Quantity for Wireless Mouse"), { target: { value: "1" } });
    fireEvent.click(screen.getByRole("button", { name: "Review server-priced cart" }));
    await screen.findByRole("button", { name: "Approve this cart" });
    fireEvent.change(screen.getByLabelText("Quantity for Wireless Mouse"), { target: { value: "20" } });
    expect(screen.queryByRole("button", { name: "Approve this cart" })).not.toBeInTheDocument();
    expect(commerce.approve).not.toHaveBeenCalled();
  });

  it("shows search failures without losing selected products", async () => {
    vi.mocked(commerce.search).mockRejectedValue(new Error("Search unavailable"));
    render(<Buyer merchantId={1} />);
    await screen.findByText("Wireless Mouse");
    fireEvent.click(screen.getByRole("button", { name: "Find my picks" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Search unavailable");
    expect(screen.getByText("Wireless Mouse")).toBeInTheDocument();
  });

  it("handles private/unavailable storefronts", async () => {
    vi.mocked(commerce.store).mockRejectedValue(new Error("Store unavailable"));
    render(<Buyer merchantId={99} standalone />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Store unavailable");
    expect(screen.queryByRole("button", { name: "Find my picks" })).not.toBeInTheDocument();
  });

  it("handles an empty catalog and disables empty cart submission", async () => {
    vi.mocked(commerce.store).mockResolvedValue({ ...storefront, products: [] });
    render(<Buyer merchantId={1} />);
    await screen.findByText("No matches within this budget. Try another search.");
    expect(screen.getByRole("button", { name: "Review server-priced cart" })).toBeDisabled();
  });

  it("searches within budget and displays the active search mode", async () => {
    render(<Buyer merchantId={1} />);
    await screen.findByText("Wireless Mouse");
    fireEvent.change(screen.getByLabelText("Shopping request"), { target: { value: "quiet mouse" } });
    fireEvent.click(screen.getByRole("button", { name: "Find my picks" }));
    await waitFor(() => expect(commerce.search).toHaveBeenCalledWith("shopper-fixture", "quiet mouse", 1000000, undefined));
    expect(await screen.findByText(/Choose products · Local search/)).toBeInTheDocument();
  });
});

it("parses paise without accepting nonfinite, fractional paise or out-of-range budgets", () => {
  expect(parseBudget("0.01")).toBe(1);
  expect(parseBudget("1000000")).toBe(100000000);
  for (const invalid of ["0", "-1", "1.001", "Infinity", "1e3", "1000000.01", ""]) expect(parseBudget(invalid)).toBeNull();
});
