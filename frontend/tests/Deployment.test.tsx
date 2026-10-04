import { readFileSync } from "node:fs";
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

describe('hosted API transport',()=>{
 const config=JSON.parse(readFileSync('vercel.json','utf8'));
 it('overrides stale cross-origin build configuration on Vercel',()=>{
   expect(config.buildCommand).toBe('VITE_API_URL= npm run build');
 });
 it('proxies nested API paths before the SPA fallback',()=>{
   expect(config.rewrites[0]).toEqual({source:'/api/:path*',destination:'https://backend-cartpilot.vercel.app/api/:path*'});
   expect(config.rewrites[1].destination).toBe('/index.html');
 });
 it('disables browser and CDN caching for authenticated API responses',()=>{
   expect(config.headers).toContainEqual({source:'/api/:path*',headers:[
     {key:'Cache-Control',value:'no-store'},
     {key:'CDN-Cache-Control',value:'no-store'},
     {key:'Vercel-CDN-Cache-Control',value:'no-store'},
   ]});
 });
});
