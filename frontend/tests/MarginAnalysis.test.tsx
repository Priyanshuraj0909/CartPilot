import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../src/App";
import { grossMargin, marginSeries } from "../src/services/margins";
import { api } from "../src/services/api";
import { catalog, fetchStore } from "./fixtures";

describe("Margin analysis workspace", () => {
  beforeEach(() => { vi.restoreAllMocks(); window.history.replaceState({}, "", "/margin-analysis"); global.fetch = vi.fn(fetchStore); });

  it("renders observed catalog margin and the guarded decision boundary", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByRole("heading", { name: "Margin Analysis" })).toBeVisible());
    await waitFor(() => expect(screen.getAllByText("49.9%").length).toBeGreaterThan(0));
    expect(screen.getByText(/Price changes still require analysis, approval/)).toBeVisible();
    expect(screen.getByRole("img", { name: /Recorded gross margin trend/ })).toBeVisible();
  });

  it("caps a comparison at four products", async () => {
    const products = Array.from({ length: 5 }, (_, index) => ({ ...catalog.products[0], id: index + 1, name: `Product ${index + 1}`, sku: `SKU-${index + 1}` }));
    vi.spyOn(api, "getProducts").mockResolvedValue({ ...catalog, products, total_products: 5 });
    render(<App />); await screen.findByText("Product 5");
    fireEvent.click(screen.getAllByRole("checkbox")[4]);
    expect(screen.getByRole("status")).toHaveTextContent("Select up to four products");
    expect(screen.getByText("4 items selected")).toBeVisible();
  });

  it("handles missing costs and an empty search without inventing a margin", async () => {
    vi.spyOn(api, "getProducts").mockResolvedValue({ ...catalog, products: [{ ...catalog.products[0], cost_price: null }] });
    render(<App />); await screen.findByText("Cost required");
    fireEvent.change(screen.getByRole("textbox", { name: "Search margin products" }), { target: { value: "unknown item" } });
    expect(screen.getByText("No products match your search.")).toBeVisible();
  });

  it("toggles the compact layout control", async () => {
    render(<App />); await screen.findByRole("heading", { name: "Margin Analysis" });
    const button = screen.getByRole("button", { name: "Edit layout" });
    fireEvent.click(button); expect(button).toHaveAttribute("aria-pressed", "true");
    await waitFor(() => expect(document.querySelector(".margin-page")).toHaveClass("compact"));
  });
});

describe("margin calculations", () => {
  it("rejects invalid and zero selling prices", () => { expect(grossMargin(0, 10)).toBeNull(); expect(grossMargin("bad", 10)).toBeNull(); expect(grossMargin(100, -1)).toBeNull(); });
  it("bounds chart history and appends the current observation", () => { const product = { ...catalog.products[0], price_history: Array.from({ length: 8 }, (_, index) => ({ id: index, old_price: 800 + index, new_price: 801 + index, changed_at: `2026-01-${String(index + 1).padStart(2, "0")}T00:00:00Z`, reason: null })) }; const points = marginSeries(product, 4); expect(points).toHaveLength(4); expect(points.at(-1)?.label).toBe("Now"); });
});
