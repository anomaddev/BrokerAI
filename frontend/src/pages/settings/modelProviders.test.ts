import { describe, expect, it } from "vitest";
import { catalogSelectionKey, parseCatalogSelectionKey } from "./modelProviders";

describe("catalogSelectionKey", () => {
  it("round-trips source id and model name", () => {
    const key = catalogSelectionKey("abc123", "grok-4.3");
    expect(key).toBe("abc123::grok-4.3");
    expect(parseCatalogSelectionKey(key)).toEqual({
      sourceId: "abc123",
      modelName: "grok-4.3",
    });
  });

  it("rejects malformed keys", () => {
    expect(parseCatalogSelectionKey("")).toBeNull();
    expect(parseCatalogSelectionKey("nosep")).toBeNull();
    expect(parseCatalogSelectionKey("::model")).toBeNull();
  });
});
