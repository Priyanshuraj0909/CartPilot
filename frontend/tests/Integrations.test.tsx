import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../src/App";
import { fetchStore, mockResponse } from "./fixtures";
import type { ShopifyStatus, ShopifySync } from "../src/types";
const connected: ShopifyStatus = {configured:true,connected:true,mode:"read_only",store:"fixture-store.myshopify.com",currency:"USD",api_version:"2026-10",message:"Connected safely.",last_sync:null};
const completed: ShopifySync = {mode:"read_only",status:"completed",started_at:"2026-10-03T01:00:00Z",completed_at:"2026-10-03T01:01:00Z",products_created:3,products_updated:0,inventory_updated:3,orders_created:1,orders_updated:0,orders_skipped:0,errors:[],warnings:[]};
function mock(status=connected, sync=completed) {
 global.fetch=vi.fn((input:RequestInfo|URL)=>String(input).includes("shopify/status")?Promise.resolve(mockResponse(status)):String(input).includes("shopify/sync")?Promise.resolve(mockResponse(sync)):fetchStore(input));
}
describe("Shopify integrations",()=>{
 beforeEach(()=>{window.history.replaceState({},"","/integrations");mock();});
 it("shows connected store and prominent read-only badge without credentials",async()=>{
  render(<App/>);expect(await screen.findByText("Connected")).toBeInTheDocument();
  expect(screen.getByText("READ ONLY")).toBeInTheDocument();expect(screen.getByText("Store: fixture-store.myshopify.com")).toBeInTheDocument();
  expect(screen.getByRole("button",{name:"Sync Now"})).toBeEnabled();expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
 });
 it("supports unconfigured stores with local demo fallback",async()=>{
  mock({...connected,configured:false,connected:false,store:null,message:"Local/demo data remains available."});render(<App/>);
  expect(await screen.findByText("Not configured")).toBeInTheDocument();expect(screen.getByRole("button",{name:"Sync Now"})).toBeDisabled();
  fireEvent.click(screen.getByRole("link",{name:"Products"}));expect(await screen.findByText("Wireless Mouse")).toBeInTheDocument();
 });
 it("shows a safe authentication failure and allows connection retest",async()=>{
  mock({...connected,connected:false,store:null,message:"Check store domain and Admin API token."});render(<App/>);
  expect(await screen.findByText("Connection failed")).toBeInTheDocument();fireEvent.click(screen.getByRole("button",{name:"Test Connection"}));
  await screen.findByText("Check store domain and Admin API token.");expect(global.fetch).toHaveBeenCalledTimes(6);
 });
 it("reports a successful sync and refreshes the local catalog",async()=>{
  render(<App/>);await screen.findByText("Connected");fireEvent.click(screen.getByRole("button",{name:"Sync Now"}));
  expect(await screen.findByText("Synchronization completed")).toBeInTheDocument();expect(screen.getByText(/Products: 3 · Inventory records: 3 · Orders: 1/)).toBeInTheDocument();
  expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining("shopify/sync"),expect.objectContaining({method:"POST",body:JSON.stringify({merchant_id:1})}));
 });
 it("shows partial failures without hiding successful counts",async()=>{
  mock(connected,{...completed,status:"partial",inventory_updated:0,errors:[{stage:"inventory",code:"network",message:"Inventory is unavailable."}]});
  render(<App/>);await screen.findByText("Connected");fireEvent.click(screen.getByRole("button",{name:"Sync Now"}));
  expect(await screen.findByText("Synchronization partial")).toBeInTheDocument();expect(screen.getByRole("alert")).toHaveTextContent("Inventory is unavailable.");
 });
 it("shows real loading state and prevents a second sync",async()=>{
  let resolve!: (response:Response)=>void;
  global.fetch=vi.fn((input:RequestInfo|URL)=>String(input).includes("shopify/sync")?new Promise<Response>(r=>{resolve=r;}):String(input).includes("shopify/status")?Promise.resolve(mockResponse(connected)):fetchStore(input));
  render(<App/>);await screen.findByText("Connected");fireEvent.click(screen.getByRole("button",{name:"Sync Now"}));
  expect(await screen.findByText("Synchronizing Shopify data...")).toBeInTheDocument();expect(screen.getByRole("button",{name:"Sync Now"})).toBeDisabled();
  resolve(mockResponse(completed));await screen.findByText("Synchronization completed");
 });
 it("keeps the page usable when sync fails",async()=>{
  global.fetch=vi.fn((input:RequestInfo|URL)=>String(input).includes("shopify/sync")?Promise.resolve(mockResponse({},503)):String(input).includes("shopify/status")?Promise.resolve(mockResponse(connected)):fetchStore(input));
  render(<App/>);await screen.findByText("Connected");fireEvent.click(screen.getByRole("button",{name:"Sync Now"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("temporarily unavailable");await waitFor(()=>expect(screen.getByRole("button",{name:"Test Connection"})).toBeEnabled());
 });
 it("shows cached summary after returning to the page",async()=>{
  mock({...connected,last_sync:completed});render(<App/>);expect(await screen.findByText("Synchronization completed")).toBeInTheDocument();
 });
});

it("shows missing Shopify cost and margin without treating them as zero",async()=>{
 const { catalog }=await import("./fixtures");
 const synced={...catalog,products:catalog.products.map(product=>({...product,source:"shopify",cost_price:null}))};
 window.history.replaceState({},"","/products");
 global.fetch=vi.fn((input:RequestInfo|URL)=>String(input).includes("/products")?Promise.resolve(mockResponse(synced)):fetchStore(input));
 render(<App/>);await screen.findByText("Wireless Mouse");
 fireEvent.click(screen.getByRole("button",{name:"Analyze Wireless Mouse"}));
 expect(await screen.findByText("Source: Shopify · local analysis cache")).toBeInTheDocument();
 expect(screen.getByText("Unknown")).toBeInTheDocument();
 expect(screen.getByText("Unavailable")).toBeInTheDocument();
});
