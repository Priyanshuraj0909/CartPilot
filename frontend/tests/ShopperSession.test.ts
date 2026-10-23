import { beforeEach, expect, it, vi } from "vitest";
import { commerce } from "../src/services/commerce";
import { mockResponse } from "./fixtures";

beforeEach(() => sessionStorage.clear());

it("deduplicates concurrent shopper initialization and persists the active token", async () => {
  const identity = { token: "shopper-fixture", expires_at: Math.floor(Date.now() / 1000) + 3600 };
  const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(mockResponse(identity));
  const values = await Promise.all([commerce.session(91), commerce.session(91)]);
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(values).toEqual([identity, identity]);
  expect(JSON.parse(sessionStorage.getItem("cartpilot-shopper-91") || "null")).toEqual(identity);
});

it("restores an unexpired capability without creating another identity", async () => {
  const identity = { token: "existing-fixture", expires_at: Math.floor(Date.now() / 1000) + 3600 };
  sessionStorage.setItem("cartpilot-shopper-92", JSON.stringify(identity));
  const fetch = vi.spyOn(globalThis, "fetch");
  expect(await commerce.session(92)).toEqual(identity);
  expect(fetch).not.toHaveBeenCalled();
});

it("replaces expired and malformed storage", async () => {
  const identity = { token: "fresh-fixture", expires_at: Math.floor(Date.now() / 1000) + 3600 };
  sessionStorage.setItem("cartpilot-shopper-93", JSON.stringify({ token: "old", expires_at: 1 }));
  sessionStorage.setItem("cartpilot-shopper-94", "invalid-json");
  vi.spyOn(globalThis, "fetch").mockImplementation(async () => mockResponse(identity));
  expect(await commerce.session(93)).toEqual(identity);
  expect(await commerce.session(94)).toEqual(identity);
});

it("clears an unsuccessful initialization so a later request can retry", async () => {
  const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(mockResponse({}, 503))
    .mockResolvedValueOnce(mockResponse({ token: "retried-fixture", expires_at: Math.floor(Date.now() / 1000) + 3600 }));
  await expect(commerce.session(95)).rejects.toThrow();
  expect((await commerce.session(95)).token).toBe("retried-fixture");
  expect(fetch).toHaveBeenCalledTimes(2);
});
