import { describe, expect, it } from "vitest";
import { mfaQrImageSrc } from "./mfaQrCode";

describe("mfaQrImageSrc", () => {
  it("wraps raw SVG so it is not treated as a relative URL", () => {
    const svg = '<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>';
    const src = mfaQrImageSrc(svg);
    expect(src?.startsWith("data:image/svg+xml;charset=utf-8,")).toBe(true);
    expect(src).not.toContain("<svg");
    expect(decodeURIComponent(src!.slice("data:image/svg+xml;charset=utf-8,".length))).toBe(svg);
  });

  it("leaves data URIs and http(s) URLs unchanged", () => {
    expect(mfaQrImageSrc("data:image/png;base64,abc")).toBe("data:image/png;base64,abc");
    expect(mfaQrImageSrc("https://example.com/qr.png")).toBe("https://example.com/qr.png");
  });

  it("returns null for empty values", () => {
    expect(mfaQrImageSrc("")).toBeNull();
    expect(mfaQrImageSrc(null)).toBeNull();
  });
});
