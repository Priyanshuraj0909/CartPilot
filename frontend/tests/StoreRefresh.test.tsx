import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { StoreProvider, useStore } from "../src/hooks/useStore";
import { api } from "../src/services/api";
import { catalog, fetchStore } from "./fixtures";

function Probe() {
  const store = useStore();
  return <><span>{store.catalog ? store.catalog.products[0]?.name : "No catalog"}</span>
    <span>{store.error}</span><span>{store.loading ? "Loading" : "Ready"}</span>
    <button onClick={store.refresh}>Refresh</button>
    <button onClick={() => store.setMerchantId(2)}>Switch merchant</button></>;
}
beforeEach(() => { vi.restoreAllMocks(); global.fetch = vi.fn(fetchStore); });
describe("store refresh", () => {
  it("keeps the current catalog visible until a refresh completes", async () => {
    render(<StoreProvider><Probe /></StoreProvider>);
    await screen.findByText("Wireless Mouse");
    let resolve!: (value: typeof catalog) => void;
    vi.spyOn(api, "getProducts").mockImplementationOnce(() => new Promise(done => { resolve = done; }));
    fireEvent.click(screen.getByText("Refresh"));
    expect(screen.getByText("Wireless Mouse")).toBeInTheDocument();
    expect(screen.getByText("Loading")).toBeInTheDocument();
    resolve({ ...catalog, products: [{ ...catalog.products[0], name: "Updated Mouse" }] });
    expect(await screen.findByText("Updated Mouse")).toBeInTheDocument();
  });
  it("retains existing data and reports a failed refresh", async () => {
    render(<StoreProvider><Probe /></StoreProvider>);
    await screen.findByText("Wireless Mouse");
    vi.spyOn(api, "getProducts").mockRejectedValueOnce(new Error("Backend offline"));
    fireEvent.click(screen.getByText("Refresh"));
    await screen.findByText("Backend offline");
    expect(screen.getByText("Wireless Mouse")).toBeInTheDocument();
  });
  it("clears previous merchant data while another merchant loads", async () => {
    render(<StoreProvider><Probe /></StoreProvider>);
    await screen.findByText("Wireless Mouse");
    vi.spyOn(api, "getProducts").mockImplementationOnce(() => new Promise(() => {}));
    fireEvent.click(screen.getByText("Switch merchant"));
    await waitFor(() => expect(screen.queryByText("Wireless Mouse")).not.toBeInTheDocument());
    expect(screen.getByText("No catalog")).toBeInTheDocument();
  });
});
