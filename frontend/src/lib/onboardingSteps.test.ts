import { describe, expect, it } from "vitest";
import { parsePreviewStep, stepIndex } from "./onboardingSteps";

describe("onboardingSteps", () => {
  it("maps step indexes", () => {
    expect(stepIndex("admin")).toBe(0);
    expect(stepIndex("data_sources")).toBe(3);
    expect(stepIndex("models")).toBe(4);
    expect(stepIndex("finish")).toBe(5);
  });

  it("parses preview step ids", () => {
    expect(parsePreviewStep("exchange")).toBe("exchange");
    expect(parsePreviewStep("models")).toBe("models");
    expect(parsePreviewStep("strategy")).toBe("data_sources");
    expect(parsePreviewStep("nope")).toBeNull();
    expect(parsePreviewStep(null)).toBeNull();
  });
});
