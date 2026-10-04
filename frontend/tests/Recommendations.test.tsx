import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { PricingCard, RestockCard, ActionPlanCard } from "../src/components/recommendations/RecommendationCards";
import { App } from "../src/App";
import { api } from "../src/services/api";
import { catalog, fetchStore, mockResponse, plan, pricing, restock } from "./fixtures";
describe("Recommendation cards", () => {
  it("renders pricing values, percentage, confidence, and risk", () => {
    render(<PricingCard data={pricing} name="Wireless Mouse" />);
    for (const text of ["₹999.00", "₹1,049.00", "+5%", "86%", "Risk: medium", "Recommendation Only"]) expect(screen.getByText(text)).toBeInTheDocument();
  });
  it("renders hold price correctly", () => { render(<PricingCard data={{ ...pricing, recommended_price: 999, price_change_percent: 0 }} />); expect(screen.getByText("Hold Price")).toBeInTheDocument(); });
  it("renders restock forecast and quantity", () => { render(<RestockCard data={restock} />); for (const text of ["8 units", "5.00/day", "1.6 days", "67 units", "Risk: high"]) expect(screen.getByText(text)).toBeInTheDocument(); });
  it("handles zero demand without rendering infinity", () => { render(<RestockCard data={{ ...restock, estimated_days_remaining: null }} />); expect(screen.getByText("No recent demand")).toBeInTheDocument(); expect(screen.queryByText(/Infinity/)).not.toBeInTheDocument(); });
  it("makes conflicts and resolution visible", () => {
    render(<ActionPlanCard data={{ ...plan, conflicts: [{ type: "pricing_inventory_conflict", product_id: 1, severity: "high", message: "Discounting may increase stockout pressure.", resolution: "Restock before discounting." }] }} productName={() => "Wireless Mouse"} />);
    expect(screen.getByText(/CONFLICT DETECTED/)).toBeInTheDocument(); expect(screen.getByText("Restock before discounting.")).toBeInTheDocument();
  });
  it("does not invent conflict warnings for compatible results", () => { render(<ActionPlanCard data={plan} productName={() => "Wireless Mouse"} />); expect(screen.getByText("No conflicts detected")).toBeInTheDocument(); expect(screen.queryByText(/CONFLICT DETECTED/)).not.toBeInTheDocument(); expect(screen.getByText(/Compatible recommendations/)).toBeInTheDocument(); });
  it("shows partial failures while preserving steps", () => { render(<ActionPlanCard data={{ ...plan, complete: false }} productName={() => "Wireless Mouse"} />); expect(screen.getByRole("alert")).toHaveTextContent("incomplete"); expect(screen.getByText("67 units proposed")).toBeInTheDocument(); });
});
describe("Live dashboard interactions", () => {
  beforeEach(() => { window.history.replaceState({}, "", "/products"); global.fetch = vi.fn(fetchStore); });
  it("loads and searches the product table", async () => {
    render(<App />); expect(await screen.findByText("Wireless Mouse")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Search products"), { target: { value: "not present" } });
    expect(screen.getByText("No products match your search.")).toBeInTheDocument();
  });
  it("shows loading while data is pending", async () => {
    vi.spyOn(api, "getProducts").mockReturnValue(new Promise(() => {})); render(<App />);
    await screen.findByText("Demo Store");
    expect(screen.getByRole("status")).toHaveTextContent("Loading store data");
  });
  it("shows friendly network errors and retry", async () => {
    vi.spyOn(api, "getProducts").mockRejectedValue(new Error("Unable to reach CartPilot. Check that the backend is running and try again."));
    render(<App />); expect(await screen.findByRole("alert")).toHaveTextContent("Unable to reach CartPilot"); expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
  it("runs pricing and restock analyses from the drawer", async () => {
    render(<App />); fireEvent.click(await screen.findByRole("button", { name: "Analyze Wireless Mouse" }));
    const dialog = screen.getByRole("dialog"); fireEvent.click(within(dialog).getByRole("button", { name: "Run Pricing Analysis" }));
    expect(await within(dialog).findByText("₹1,049.00")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Run Restock Analysis" }));
    expect(await within(dialog).findByText("67 units")).toBeInTheDocument();
    fireEvent.keyDown(dialog, { key: "Escape" }); expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
  it("sends selected products and goal to the orchestrator", async () => {
    window.history.replaceState({}, "", "/ai-manager"); render(<App />);
    const checkbox = await screen.findByRole("checkbox"); fireEvent.click(checkbox);
    fireEvent.click(screen.getByRole("button", { name: "Analyze with CartPilot" }));
    expect(await screen.findByText("67 units proposed")).toBeInTheDocument();
    expect(screen.getByText(/Human approval required/)).toBeInTheDocument();
    const calls = vi.mocked(global.fetch).mock.calls;
    const call = calls.find(([input]) => String(input).includes("orchestrate"));
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ merchant_id: 1, goal: "balanced_growth", product_ids: [1] });
  });
  it("disables analysis with no selection", async () => { window.history.replaceState({}, "", "/ai-manager"); render(<App />); await screen.findByRole("checkbox"); expect(screen.getByRole("button", { name: "Analyze with CartPilot" })).toBeDisabled(); });
  it("navigation and browser history display the correct page", async () => {
    render(<App />); await screen.findByText("Wireless Mouse"); fireEvent.click(screen.getByRole("link", { name: "Agent Activity" }));
    expect(screen.getByRole("heading", { name: "Agent Activity" })).toBeInTheDocument(); expect(screen.queryByText("Coming Soon")).not.toBeInTheDocument();
    window.history.replaceState({}, "", "/inventory"); fireEvent.popState(window);
    expect(screen.getByRole("heading", { name: "Inventory" })).toBeInTheDocument();
  });
  it("does not provide execution controls", async () => {
    render(<App />); fireEvent.click(await screen.findByRole("button", { name: "Analyze Wireless Mouse" }));
    expect(screen.queryByRole("button", { name: /Apply Price|Restock Now|Purchase Order|Approve|Launch Promotion|Publish Listing/i })).not.toBeInTheDocument();
  });
  it("shows the persisted empty state accurately", async () => { window.history.replaceState({}, "", "/recommendations"); render(<App />); expect(await screen.findByText(/No persisted recommendations match/)).toBeInTheDocument(); });
  it("does not silently replace an empty catalogue with demo values", async () => {
    global.fetch = vi.fn(input => String(input).includes("products") ? Promise.resolve(mockResponse({ ...catalog, products: [], total_products: 0 })) : fetchStore(input));
    render(<App />); expect(await screen.findByText(/No products found/)).toBeInTheDocument(); expect(screen.queryByText("Wireless Mouse")).not.toBeInTheDocument();
  });
  it("handles API validation errors without exposing internal traces", async () => {
    window.history.replaceState({}, "", "/ai-manager"); global.fetch = vi.fn(input => String(input).includes("orchestrate") ? Promise.resolve(mockResponse({ detail: "internal stacktrace" }, 422)) : fetchStore(input));
    render(<App />); fireEvent.click(await screen.findByRole("checkbox")); fireEvent.click(screen.getByRole("button", { name: "Analyze with CartPilot" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("could not be validated"); expect(screen.queryByText("internal stacktrace")).not.toBeInTheDocument();
  });
});


describe("Saved recommendations and merchant changes", () => {
  beforeEach(() => { window.history.replaceState({}, "", "/recommendations"); global.fetch = vi.fn(fetchStore); });
  it("renders saved proposals and filters recorded status", async () => {
    global.fetch = vi.fn(input => String(input).includes("/recommendations") ? Promise.resolve(mockResponse([
      { id: 1, product_id: 1, product_name: "Wireless Mouse", agent: "pricing", title: "Saved mouse proposal", description: "Review price", confidence: .86, risk_level: "medium", status: "pending", created_at: "2026-10-03T10:00:00Z", payload: pricing },
    ])) : fetchStore(input));
    render(<App />); expect(await screen.findByText("Saved mouse proposal")).toBeInTheDocument();
    expect(screen.getByText("pending", { selector: "span" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "rejected" } });
    expect(screen.queryByText("Saved mouse proposal")).not.toBeInTheDocument();
    expect(screen.getByText(/No persisted recommendations match/)).toBeInTheDocument();
  });
  it("clears previous merchant data immediately on selection", async () => {
    window.history.replaceState({}, "", "/products");
    global.fetch = vi.fn(input => {
      const path = String(input);
      if (path.includes("merchants")) return Promise.resolve(mockResponse([{ id: 1, name: "One", store_name: "Store One" }, { id: 2, name: "Two", store_name: "Store Two" }]));
      if (path.includes("products") && path.includes("merchant_id=2")) return Promise.resolve(mockResponse({ ...catalog, products: [], total_products: 0 }));
      return fetchStore(input);
    });
    render(<App />); await screen.findByText("Wireless Mouse");
    fireEvent.change(screen.getByRole("combobox", { name: "Merchant" }), { target: { value: "2" } });
    expect(screen.queryByText("Wireless Mouse")).not.toBeInTheDocument();
    expect(await screen.findByText(/No products found/)).toBeInTheDocument();
  });
});
