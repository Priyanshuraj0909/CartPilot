import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, SHOPIFY_PRODUCTION_MESSAGE } from "../src/services/api";
import { mockResponse } from "./fixtures";
const gate = "Phase 9 local actions are available only in development/test environments.";
afterEach(() => vi.unstubAllGlobals());
describe("safe API permission errors", () => {
  it("reports the hosted action restriction without claiming merchant ownership failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(mockResponse({detail:gate}, 403)));
    await expect(api.reviewAction(1, 1, true, "review")).rejects.toMatchObject({
      status:403, message:"Action creation, approval and execution are disabled in this hosted advisory demo.",
    });
  });
  it("recognizes the hosted Shopify gate for synchronization", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(mockResponse({detail:gate}, 403)));
    await expect(api.syncShopify(1)).rejects.toMatchObject({status:403,message:SHOPIFY_PRODUCTION_MESSAGE});
  });
  it("retains a real product ownership denial", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(mockResponse({detail:"Product does not belong to the selected merchant."}, 403)));
    await expect(api.getPricingRecommendation(1, 2)).rejects.toThrow("This product does not belong to the selected merchant.");
  });
  it.each([mockResponse({detail:"private-password"},403), new Response("<html>private-token</html>",{status:403})])(
    "does not echo unknown JSON or provider HTML errors", async response => {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
      const error = await api.getShopifyStatus(1).catch(error => error as ApiError);
      expect(error).toBeInstanceOf(ApiError);
      expect(error).toMatchObject({status:403,message:"This request is not permitted for the selected merchant or deployment."});
    },
  );
});
