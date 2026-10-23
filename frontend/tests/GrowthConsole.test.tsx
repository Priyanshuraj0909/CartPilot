import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { GrowthConsole } from "../src/pages/GrowthConsole";
import { commerce } from "../src/services/commerce";

vi.mock("../src/hooks/useStore", () => ({ useStore: () => ({ merchantId: 1, refresh: vi.fn(), catalog: { products: [{ id: 1, name: "Mouse" }] } }) }));
const policy = { published: false, max_spend_paise: 100000, blocked_categories: [], boosted_product_ids: [] };
beforeEach(() => {
  vi.spyOn(commerce, "policy").mockResolvedValue(policy);
  vi.spyOn(commerce, "growth").mockResolvedValue({ counts: { simulated: 2 }, test_paid_value_paise: 0, real_revenue_paise: 0, recovery: [], recommendation_method: "Explainable ranking", limitations: "Test only" });
  vi.spyOn(commerce, "savePolicy").mockImplementation(async value => value);
});

it("saves explicit storefront publication and keeps test metrics labeled", async () => {
  render(<GrowthConsole />);
  const publish = await screen.findByRole("checkbox", { name: /Publish public storefront/ });
  fireEvent.click(publish);
  fireEvent.click(screen.getByRole("button", { name: "Save storefront policies" }));
  await screen.findByText("Storefront policies saved.");
  expect(commerce.savePolicy).toHaveBeenCalledWith({ ...policy, published: true });
  expect(screen.getByText(/not real revenue/)).toBeInTheDocument();
});

it("shows private merchant API failures", async () => {
  vi.mocked(commerce.policy).mockRejectedValue(new Error("Sign in to manage commerce."));
  render(<GrowthConsole />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Sign in");
});

it("imports reviewed CSV and reports the actual imported count", async () => {
  vi.spyOn(commerce, "importCatalog").mockResolvedValue({ imported: 1 });
  render(<GrowthConsole />);
  await screen.findByRole("checkbox", { name: /Publish public storefront/ });
  const csv = "sku,name,category,description,cost_price,selling_price,quantity\nA,Notebook,Books,Plain,50,100,25";
  fireEvent.change(screen.getByLabelText("Catalog CSV preview"), { target: { value: csv } });
  fireEvent.click(screen.getByRole("button", { name: "Import new products" }));
  await screen.findByText("1 products imported.");
  expect(commerce.importCatalog).toHaveBeenCalledWith(csv);
});

it("reports insufficient training history without claiming success", async () => {
  vi.spyOn(commerce, "train").mockRejectedValue(new Error("Insufficient completed orders"));
  render(<GrowthConsole />);
  await screen.findByRole("checkbox", { name: /Publish public storefront/ });
  fireEvent.click(screen.getByRole("button", { name: "Train co-purchase model" }));
  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Insufficient completed orders"));
});
