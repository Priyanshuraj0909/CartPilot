import {render, screen} from "@testing-library/react";
import {describe, it, expect, vi, afterEach} from "vitest";
import {ErrorBoundary} from "../src/components/ErrorBoundary";

afterEach(() => { vi.unstubAllEnvs(); vi.restoreAllMocks(); vi.resetModules(); });
describe("Deployment", () => {
  it.each([
    [false, "", "http://localhost:8000"],
    [true, "https://api.example.test/", "https://api.example.test"],
    [true, "", ""],
  ])("uses environment configuration (production=%s, url=%s)", async (production, url, expected) => {
    vi.stubEnv("PROD", production); vi.stubEnv("VITE_API_URL", url);
    vi.resetModules();
    global.fetch = vi.fn().mockResolvedValue({ok: true, json: async () => ({status: "ok"})});
    const {api} = await import("../src/services/api");
    await api.getHealth();
    expect(global.fetch).toHaveBeenCalledWith(`${expected}/api/v1/health/detailed`, expect.any(Object));
  });
  it("shows children normally", () => {
    render(<ErrorBoundary><p>Dashboard ready</p></ErrorBoundary>);
    expect(screen.getByText("Dashboard ready")).toBeVisible();
  });
  it("renders recovery controls without raw exception details", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    function Broken(): never { throw new Error("private-render-details"); }
    render(<ErrorBoundary><Broken/></ErrorBoundary>);
    expect(screen.getByRole("alert")).toHaveTextContent("could not display this page");
    expect(screen.queryByText("private-render-details")).toBeNull();
    expect(screen.getByRole("button", {name: "Reload page"})).toBeVisible();
  });
});
