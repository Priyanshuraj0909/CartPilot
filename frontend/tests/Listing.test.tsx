import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ListingCard, ActionPlanCard } from "../src/components/recommendations/RecommendationCards";
import { App } from "../src/App";
import type { ListingRecommendation } from "../src/types";
import { fetchStore, mockResponse, plan, catalog } from "./fixtures";
const listing: ListingRecommendation = { product_id: 1, current_title: "Wireless Mouse", recommended_title: "Wireless Mouse — 2.4 GHz wireless mouse with USB receiver", current_description: "2.4 GHz wireless mouse with USB receiver", recommended_description: "2.4 GHz wireless mouse with USB receiver", issues: ["Title lacks descriptive detail", "Description is too short"], suggestions: ["Verify and add power details if applicable."], missing_attributes: ["power"], quality_score: .48, recommended_keywords: ["wireless", "mouse"], category_consistency: "consistent", confidence: .9, risk_level: "medium", reason: "Review listing completeness before considering content changes." };
describe("Listing experience", () => {
  beforeEach(() => { window.history.replaceState({},"","/products"); global.fetch=vi.fn(input => String(input).includes("/listing/") ? Promise.resolve(mockResponse(listing)) : fetchStore(input)); });
  it("shows current and recommended text, issues and evidence", () => {
    render(<ListingCard data={listing} />);
    for(const text of ["Current title", "Recommended title", "Current description", "Recommended description", listing.recommended_title, "48%", "90%", "Risk: medium", "Recommendation Only", listing.issues[0]]) expect(screen.getByText(text)).toBeInTheDocument();
    expect(screen.queryByRole("button",{name:/Apply Listing|Publish|Update Product/})).not.toBeInTheDocument();
  });
  it("handles missing descriptions and listings without issues", () => {
    render(<ListingCard data={{...listing,current_description:null,issues:[],suggestions:[]}} />);
    expect(screen.getByText("No description recorded")).toBeInTheDocument();
    expect(screen.getByText("No major issues detected.")).toBeInTheDocument();
  });
  it("runs a scoped listing analysis and retains the session result", async () => {
    render(<App />);fireEvent.click(await screen.findByRole("button",{name:"Analyze Wireless Mouse"}));
    fireEvent.click(screen.getByRole("button",{name:"Run Listing Analysis"}));
    expect(await screen.findByText(listing.recommended_title)).toBeInTheDocument();
    const call=vi.mocked(global.fetch).mock.calls.find(([input]) => String(input).includes("/listing/"));
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({product_id:1,merchant_id:1});
    fireEvent.keyDown(screen.getByRole("dialog"),{key:"Escape"});fireEvent.click(screen.getByRole("link",{name:"Recommendations"}));
    fireEvent.change(screen.getByLabelText("Agent"),{target:{value:"listing"}});
    expect(screen.getByText(listing.recommended_title)).toBeInTheDocument();
  });
  it("allows listing analysis even when inventory is missing", async () => {
    global.fetch=vi.fn(input => String(input).includes("/products") ? Promise.resolve(mockResponse({...catalog,products:catalog.products.map(p=>({...p,inventory:null}))})) : fetchStore(input));
    render(<App />);fireEvent.click(await screen.findByRole("button",{name:"Analyze Wireless Mouse"}));
    expect(screen.getByRole("button",{name:"Run Listing Analysis"})).toBeEnabled();
  });
  it("shows a friendly failed-analysis state", async () => {
    global.fetch=vi.fn(input => String(input).includes("/listing/") ? Promise.resolve(mockResponse({},503)) : fetchStore(input));
    render(<App />);fireEvent.click(await screen.findByRole("button",{name:"Analyze Wireless Mouse"}));
    fireEvent.click(screen.getByRole("button",{name:"Run Listing Analysis"}));
    expect(await screen.findByRole("alert")).toHaveTextContent("could not complete");
  });
  it("renders listing results and next steps inside a coordinated plan", () => {
    render(<ActionPlanCard data={{...plan,selected_agents:["listing"],recommendations:[{agent:"listing",product_id:1,priority:"low",action:"review_listing",recommended_price:null,recommended_quantity:null,deferred:false,coordination_reason:listing.reason}],agent_results:[{agent_name:"listing",product_id:1,success:true,recommendation:listing,confidence:listing.confidence,risk_level:listing.risk_level,error:null}]}} productName={()=>"Wireless Mouse"} />);
    expect(screen.getByText(/Review listing quality/)).toBeInTheDocument();
    expect(screen.getByText(listing.recommended_title)).toBeInTheDocument();
  });
  it("shows all five agents active", async () => {
    window.history.replaceState({},"","/agent-activity");render(<App />);await screen.findByText("Demo Store");
    const heading=screen.getByRole("heading",{name:"Listing Agent"});expect(within(heading.closest("article")!).getByText("Active")).toBeInTheDocument();
    expect(screen.getAllByText("Active")).toHaveLength(5);expect(screen.queryByText("Coming Soon")).not.toBeInTheDocument();
  });
  it("offers listing goals in AI Manager", async () => {
    window.history.replaceState({},"","/ai-manager");render(<App />);await screen.findByRole("checkbox");
    expect(screen.getByRole("option",{name:/improve product listings/i})).toBeInTheDocument();
    expect(screen.getByRole("option",{name:/improve product performance/i})).toBeInTheDocument();
  });
});
