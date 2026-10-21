import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { AgentActivity } from "../src/pages/AgentActivity";
import type { AgentRun } from "../src/types";
import { mockResponse } from "./fixtures";

const state = { merchantId: 1, analyses: [], error: "" };
vi.mock("../src/hooks/useStore", () => ({ useStore: () => state }));

const run: AgentRun = {
  id: 1, merchant_id: 1, agent_name: "orchestrator", status: "completed",
  started_at: "2026-10-21T10:00:00Z", completed_at: "2026-10-21T10:00:01Z",
  input_summary: { goal: "balanced_growth" },
  output_summary: { summary: "Saved store plan", complete: true, products_analyzed: 3, recommendations: 4, failed_analyses: 0 }, error_message: null,
};

beforeEach(() => { state.merchantId = 1; state.error = ""; });

it("loads saved plans without requiring session analysis", async () => {
  global.fetch = vi.fn().mockImplementation(async () => mockResponse([run]));
  const view = render(<AgentActivity />);
  expect(await screen.findByText("Saved store plan")).toBeVisible();
  expect(screen.getByText("3 products · 0 failed analyses")).toBeVisible();
  expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining("/agent-runs?merchant_id=1&offset=0"), expect.anything());
  view.unmount();
  render(<AgentActivity />);
  expect(await screen.findByText("Saved store plan")).toBeVisible();
});

it("shows a useful empty state", async () => {
  global.fetch = vi.fn().mockResolvedValue(mockResponse([]));
  render(<AgentActivity />);
  expect(await screen.findByText("No saved plans for this merchant. Run AI Manager to begin.")).toBeVisible();
});

it("makes partial failures visible", async () => {
  global.fetch = vi.fn().mockResolvedValue(mockResponse([{ ...run, output_summary: { ...run.output_summary, complete: false, failed_analyses: 2 } }]));
  render(<AgentActivity />);
  expect(await screen.findByText("Partial result")).toBeVisible();
  expect(screen.getByText("3 products · 2 failed analyses")).toBeVisible();
});

it("recovers from an activity load failure", async () => {
  global.fetch = vi.fn().mockRejectedValueOnce(new TypeError("network")).mockResolvedValue(mockResponse([run]));
  render(<AgentActivity />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Unable to reach");
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByText("Saved store plan")).toBeVisible();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

it("loads the next bounded page without losing earlier plans", async () => {
  const first = Array.from({ length: 50 }, (_, i) => ({ ...run, id: i + 1 }));
  global.fetch = vi.fn().mockResolvedValueOnce(mockResponse(first)).mockResolvedValueOnce(mockResponse([{ ...run, id: 51, output_summary: { ...run.output_summary, summary: "Older store plan" } }]));
  render(<AgentActivity />);
  fireEvent.click(await screen.findByRole("button", { name: "Load more activity" }));
  expect(await screen.findByText("Older store plan")).toBeVisible();
  expect(screen.getAllByText("Saved store plan")).toHaveLength(50);
  expect(global.fetch).toHaveBeenLastCalledWith(expect.stringContaining("offset=50"), expect.anything());
  expect(screen.queryByRole("button", { name: "Load more activity" })).not.toBeInTheDocument();
});

it("clears previous merchant plans and ignores a late response", async () => {
  let finish: (value: Response) => void = () => {};
  global.fetch = vi.fn().mockImplementationOnce(() => new Promise<Response>(resolve => { finish = resolve; })).mockResolvedValueOnce(mockResponse([]));
  const view = render(<AgentActivity />);
  await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(1));
  state.merchantId = 2;
  view.rerender(<AgentActivity />);
  expect(await screen.findByText("No saved plans for this merchant. Run AI Manager to begin.")).toBeVisible();
  await act(async () => { finish(mockResponse([run])); });
  expect(screen.queryByText("Saved store plan")).not.toBeInTheDocument();
});
