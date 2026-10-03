import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { PromotionCard, ActionPlanCard } from "../src/components/recommendations/RecommendationCards";
import { App } from "../src/App";
import type { PromotionRecommendation } from "../src/types";
import { fetchStore, mockResponse, plan } from "./fixtures";
const promotion: PromotionRecommendation = { product_id: 1, current_price: 1499, cost_price: 850, promotion_recommended: true, promotion_type: "discount", discount_percentage: 10, promotional_price: 1349.1, reason: "High inventory with declining demand supports review.", confidence: .75, risk_level: "medium", available_inventory: 120, sales_velocity: 1.21, sales_trend: "declining", gross_margin_percent: 43.3, retained_margin_percent: 37, days_of_inventory: 98.8, recent_units: 1, previous_units: 16, expected_effect: "May improve sell-through; revenue lift is not guaranteed." };
describe("Promotion experience", () => {
  beforeEach(() => { window.history.replaceState({}, "", "/products"); global.fetch = vi.fn(input => String(input).includes("/promotion/") ? Promise.resolve(mockResponse(promotion)) : fetchStore(input)); });
  it("shows discount economics, evidence, trend and advisory status", () => {
    render(<PromotionCard data={promotion} name="Bluetooth Speaker" />);
    for (const text of ["Bluetooth Speaker", "10% Discount", "$1,349.10", "120 units", "declining", "37.0%", "75%", "Recommendation Only"]) expect(screen.getByText(text)).toBeInTheDocument();
  });
  it("shows a blocked promotion clearly", () => {
    render(<PromotionCard data={{ ...promotion, promotion_recommended: false, promotion_type: "none", discount_percentage: 0, promotional_price: 1499 }} />);
    expect(screen.getByText("No promotion recommended")).toBeInTheDocument();
  });
  it("runs a merchant-scoped promotion from the product drawer and retains its session result", async () => {
    render(<App />); fireEvent.click(await screen.findByRole("button", { name: "Analyze Wireless Mouse" }));
    const dialog=screen.getByRole("dialog");fireEvent.click(within(dialog).getByRole("button", { name: "Run Promotion Analysis" }));
    expect(await within(dialog).findByText("10% Discount")).toBeInTheDocument();
    const call=vi.mocked(global.fetch).mock.calls.find(([input]) => String(input).includes("/promotion/"));
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ product_id: 1, merchant_id: 1 });
    fireEvent.keyDown(dialog,{key:"Escape"});fireEvent.click(screen.getByRole("link",{name:"Recommendations"}));
    expect(screen.getByText("10% Discount")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Agent"),{target:{value:"promotion"}});
    expect(screen.getByText("10% Discount")).toBeInTheDocument();
    expect(screen.queryByRole("button", {name:/Apply Discount|Launch Promotion|Publish Promotion/i})).not.toBeInTheDocument();
  });
  it("shows promotion errors without claiming a result", async () => {
    global.fetch=vi.fn(input => String(input).includes("/promotion/") ? Promise.resolve(mockResponse({},422)) : fetchStore(input));
    render(<App />);fireEvent.click(await screen.findByRole("button",{name:"Analyze Wireless Mouse"}));
    fireEvent.click(screen.getByRole("button",{name:"Run Promotion Analysis"}));
    expect(await screen.findByRole("alert")).toHaveTextContent("could not be validated");
    expect(screen.queryByText("10% Discount")).not.toBeInTheDocument();
  });
  it("renders promotion conflicts and deferred coordinated steps", () => {
    render(<ActionPlanCard data={{...plan,selected_agents:["pricing","restock","promotion"],conflicts:[{type:"promotion_inventory_conflict",product_id:1,severity:"high",message:"Promotion conflicts with stockout exposure.",resolution:"Replenish inventory before stimulating demand."}],recommendations:[{agent:"promotion",product_id:1,priority:"low",action:"no_promotion",recommended_price:1499,recommended_quantity:null,deferred:true,coordination_reason:"Resolve inventory first."}],agent_results:[{agent_name:"promotion",product_id:1,success:true,recommendation:promotion,confidence:.75,risk_level:"medium",error:null}]}} productName={()=>"Bluetooth Speaker"} />);
    expect(screen.getByText("Replenish inventory before stimulating demand.")).toBeInTheDocument();
    expect(screen.getByText("Deferred")).toBeInTheDocument();expect(screen.getByText(/Hold promotion/)).toBeInTheDocument();
    expect(screen.getByText("10% Discount")).toBeInTheDocument();
  });
  it("marks Promotion and Listing active", async () => {
    window.history.replaceState({},"","/agent-activity");render(<App />);await screen.findByText("Demo Store");
    const heading=screen.getByRole("heading",{name:"Promotion Agent"});expect(within(heading.closest("article")!).getByText("Active")).toBeInTheDocument();
    expect(screen.getByRole("heading",{name:"Listing Agent"})).toBeInTheDocument();
    expect(screen.queryByText("Coming Soon")).not.toBeInTheDocument();
  });
  it("offers promotion-only goals in AI Manager", async () => {
    window.history.replaceState({},"","/ai-manager");render(<App />);await screen.findByRole("checkbox");
    expect(screen.getByRole("option",{name:/reduce excess inventory/i})).toBeInTheDocument();
    expect(screen.getByRole("option",{name:/increase revenue while maintaining healthy inventory/i})).toBeInTheDocument();
  });
});
