import {render,screen,fireEvent,act} from "@testing-library/react";
import {describe,it,expect,vi} from "vitest";
import {App} from "../src/App";
import {fetchStore} from "./fixtures";
describe("Release failure and scope checks",()=>{
 it.each(["/integrations","/approvals","/action-history"])("shows initial backend failure on %s",async(path)=>{
  window.history.replaceState({},"",path);
  global.fetch=vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));render(<App/>);
  expect(await screen.findByRole("alert")).toHaveTextContent("Unable to reach CartPilot");
 });
 it.each(["Pricing","Restock"])("sends merchant scope with %s requests",async(agent)=>{
  window.history.replaceState({},"","/products");global.fetch=vi.fn(fetchStore);render(<App/>);
  fireEvent.click(await screen.findByRole("button",{name:"Analyze Wireless Mouse"}));
  await act(async()=>{fireEvent.click(screen.getByRole("button",{name:`Run ${agent} Analysis`}));});
  expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining(`/${agent.toLowerCase()}/recommend`),expect.objectContaining({body:JSON.stringify({product_id:1,merchant_id:1})}));
 });
});
