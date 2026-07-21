import { describe, expect, it } from "vitest";
import { buildBacktestFeedbackPrintDocument } from "./exportBacktestFeedbackPdf";

describe("buildBacktestFeedbackPrintDocument", () => {
  it("escapes title and meta while preserving body HTML", () => {
    const html = buildBacktestFeedbackPrintDocument({
      title: `EMA <Cross> & "AI"`,
      subtitle: "EUR/USD · M15",
      metaLines: ["gpt-4o", "Finished <now>"],
      bodyHtml: "<h2>Summary</h2><p>Improve <strong>filters</strong>.</p>",
    });

    expect(html).toContain("EMA &lt;Cross&gt; &amp; &quot;AI&quot;");
    expect(html).toContain("Finished &lt;now&gt;");
    expect(html).toContain("<h2>Summary</h2><p>Improve <strong>filters</strong>.</p>");
    expect(html).toContain("<title>EMA &lt;Cross&gt; &amp; &quot;AI&quot;</title>");
  });

  it("omits empty subtitle and meta blocks", () => {
    const html = buildBacktestFeedbackPrintDocument({
      title: "Feedback",
      bodyHtml: "<p>Hi</p>",
    });
    expect(html).not.toContain('class="subtitle"');
    expect(html).not.toContain('class="meta"');
    expect(html).toContain("<p>Hi</p>");
  });
});
