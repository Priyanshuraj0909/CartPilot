import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { Dashboard } from "../src/pages/Dashboard";

describe("Dashboard Component", () => {
  beforeEach(() => {
    // Mock fetch for health checks
    global.fetch = vi.fn().mockImplementation(() =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            status: "ok",
            app: "CartPilot",
            environment: "development",
            database: "connected",
            redis: "connected",
            version: "1.0.0",
          }),
      })
    );
  });

  it("renders the CartPilot title and AI Manager badge", async () => {
    render(<Dashboard />);
    expect(screen.getByText("CartPilot")).toBeInTheDocument();
    expect(screen.getByText("AI Manager")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId("health-badge")).toBeInTheDocument();
    });
  });

  it("renders all four required Phase 1 metric cards", async () => {
    render(<Dashboard />);

    // Check titles
    expect(screen.getByText("Revenue")).toBeInTheDocument();
    expect(screen.getByText("Orders")).toBeInTheDocument();
    expect(screen.getByText("Inventory")).toBeInTheDocument();
    expect(screen.getByText("AI Recommendations")).toBeInTheDocument();

    // Check mock values
    expect(screen.getByText("$124,500")).toBeInTheDocument();
    expect(screen.getByText("1,420")).toBeInTheDocument();
    expect(screen.getByText("3,850")).toBeInTheDocument();
    expect(screen.getByText("3 Pending")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByTestId("health-badge")).toBeInTheDocument();
    });
  });

  it("renders the health badge status", async () => {
    render(<Dashboard />);
    await waitFor(() => {
      expect(screen.getByText("API Connected")).toBeInTheDocument();
    });
  });

  it("renders the Phase 1 infrastructure diagnostics block", async () => {
    render(<Dashboard />);
    expect(
      screen.getByText("Phase 1 Infrastructure Diagnostics")
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId("health-badge")).toBeInTheDocument();
    });
  });
});
