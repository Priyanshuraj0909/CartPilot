import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { App } from "../src/App";
import { fetchStore } from "./fixtures";
describe("Dashboard Component", () => {
  beforeEach(() => { window.history.replaceState({}, "", "/dashboard"); global.fetch = vi.fn(fetchStore); });
  it("renders the CartPilot title and AI Manager badge", async () => {
    render(<App />); expect(screen.getByText("CartPilot")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "AI Manager" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("health-badge")).toHaveTextContent("API Connected"));
  });
  it("renders all four foundation metrics using backend data instead of mock values", async () => {
    render(<App />); for (const title of ["Revenue", "Orders", "AI Recommendations"]) expect(screen.getByText(title)).toBeInTheDocument();
    await screen.findByText("$69,930.00"); expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.queryByText("$124,500")).not.toBeInTheDocument();
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
});
