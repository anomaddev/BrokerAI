import { describe, expect, it } from "vitest";
import { takeProfitModeOptions, trailModeOptions } from "./catalog";

describe("takeProfitModeOptions", () => {
  it("puts reverse crossover first when EMA signal is active", () => {
    const options = takeProfitModeOptions(true);
    expect(options[0]?.value).toBe("reverse_crossover");
    expect(options.map((option) => option.value)).toContain("trailing_stop");
  });

  it("hides reverse crossover when EMA signal is inactive", () => {
    const options = takeProfitModeOptions(false);
    expect(options.map((option) => option.value)).not.toContain("reverse_crossover");
    expect(options[0]?.value).toBe("fixed_pips");
  });
});

describe("trailModeOptions", () => {
  it("puts Trail EMA Slow first when EMA signal is active", () => {
    const options = trailModeOptions(true);
    expect(options[0]?.value).toBe("ema_slow");
    expect(options.map((option) => option.value)).toContain("atr");
  });

  it("hides Trail EMA Slow when EMA signal is inactive", () => {
    const options = trailModeOptions(false);
    expect(options.map((option) => option.value)).toEqual(["atr"]);
  });
});
