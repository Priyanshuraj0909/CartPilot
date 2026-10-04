import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { api } from "../src/services/api";
import { App } from "../src/App";
import { catalog, fetchStore } from "./fixtures";
describe("Dashboard Component", () => {
  beforeEach(() => { vi.restoreAllMocks(); window.history.replaceState({}, "", "/dashboard"); global.fetch = vi.fn(fetchStore); });
  it("renders the CartPilot title and AI Manager badge", async () => {
    render(<App />); expect(screen.getByText("CartPilot")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "AI Manager" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("health-badge")).toHaveTextContent("API Connected"));
  });
  it("renders all four foundation metrics using backend data instead of mock values", async () => {
    render(<App />); for (const title of ["Revenue", "Orders", "AI Recommendations"]) expect(screen.getByText(title)).toBeInTheDocument();
    await screen.findByText("₹69,930.00"); expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.queryByText("₹124,500")).not.toBeInTheDocument();
  });
  it("renders the health badge status", async () => { render(<App />); expect(await screen.findByText("API Connected")).toBeInTheDocument(); });
  it("makes merchant management discoverable from the dashboard", async () => {
    render(<App />);
    expect(screen.getByRole("button", { name: "Import sales & view insights" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "View stock notifications" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Add or edit products" }));
    expect(window.location.pathname).toBe("/store-management");
    await waitFor(() => expect(screen.getByText("Sign in or create a merchant account to manage your own products, import sales and view alerts.")).toBeInTheDocument());
  });
  it("renders infrastructure diagnostics from the health endpoint", async () => {
    render(<App />); expect(await screen.findByText("Database: connected")).toBeInTheDocument();
    expect(screen.getByText("Redis: connected")).toBeInTheDocument();
    expect(screen.getByText("Backend: Reachable")).toBeInTheDocument();
  });
  it("searches beyond the six-product preview from the top of the dashboard", async () => {
    const products = Array.from({length: 7}, (_, i) => ({...catalog.products[0], id:i+1, name:i===6 ? "Seventh Test Mouse" : `Product ${i+1}`, sku:`TEST-${i+1}`}));
    vi.spyOn(api,"getProducts").mockResolvedValue({...catalog,products,total_products:7});
    render(<App />);
    await screen.findByText("Product 1");
    expect(screen.queryByText("Seventh Test Mouse")).not.toBeInTheDocument();
    const search=screen.getByRole("searchbox",{name:"Search products"});
    expect(screen.getAllByRole("searchbox",{name:"Search products"})).toHaveLength(1);
    fireEvent.change(search,{target:{value:"  seventh test mouse  "}});
    expect(screen.getByText("Seventh Test Mouse")).toBeInTheDocument();
    expect(screen.queryByText("Product 1")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button",{name:"Clear search"}));
    expect(search).toHaveValue("");
    expect(screen.getByText("Product 1")).toBeInTheDocument();
  });
  it("shows a dashboard no-match message without navigating away", async () => {
    render(<App />);
    await screen.findByText("Wireless Mouse");
    fireEvent.change(screen.getByRole("searchbox",{name:"Search products"}),{target:{value:"does not exist"}});
    expect(screen.getByText("No products match your search.")).toBeInTheDocument();
    expect(window.location.pathname).toBe("/dashboard");
  });
});
