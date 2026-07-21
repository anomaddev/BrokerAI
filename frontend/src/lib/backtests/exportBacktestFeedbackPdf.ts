/**
 * Open a print-friendly window for AI backtest feedback so the user can
 * Save as PDF from the browser print dialog.
 */

export type BacktestFeedbackPrintOptions = {
  title: string;
  subtitle?: string;
  metaLines?: string[];
  /** Sanitized HTML from the already-rendered markdown body. */
  bodyHtml: string;
};

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** Build the standalone HTML document used for print / Save as PDF. */
export function buildBacktestFeedbackPrintDocument(
  options: BacktestFeedbackPrintOptions,
): string {
  const title = escapeHtml(options.title.trim() || "AI feedback");
  const subtitle = options.subtitle?.trim()
    ? `<p class="subtitle">${escapeHtml(options.subtitle.trim())}</p>`
    : "";
  const meta =
    options.metaLines && options.metaLines.length > 0
      ? `<p class="meta">${options.metaLines
          .map((line) => escapeHtml(line))
          .join(" · ")}</p>`
      : "";

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>${title}</title>
  <style>
    :root {
      color-scheme: light;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      padding: 2rem 2.25rem 2.5rem;
      font-family: "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif;
      font-size: 11.5pt;
      line-height: 1.55;
      color: #1a1a1a;
      background: #fff;
    }
    header {
      margin-bottom: 1.5rem;
      padding-bottom: 1rem;
      border-bottom: 1px solid #d0d0d0;
    }
    h1 {
      margin: 0;
      font-size: 1.55rem;
      font-weight: 700;
      letter-spacing: -0.02em;
      line-height: 1.25;
    }
    .subtitle {
      margin: 0.4rem 0 0;
      font-size: 0.95rem;
      color: #333;
    }
    .meta {
      margin: 0.45rem 0 0;
      font-family: ui-sans-serif, system-ui, -apple-system, sans-serif;
      font-size: 0.78rem;
      color: #666;
    }
    .body h1, .body h2, .body h3, .body h4 {
      font-family: ui-sans-serif, system-ui, -apple-system, sans-serif;
      line-height: 1.3;
      margin: 1.35em 0 0.45em;
    }
    .body h1 { font-size: 1.35rem; }
    .body h2 { font-size: 1.15rem; }
    .body h3 { font-size: 1.05rem; }
    .body h4 { font-size: 1rem; }
    .body p { margin: 0.65em 0; }
    .body ul, .body ol { margin: 0.55em 0; padding-left: 1.4em; }
    .body li { margin: 0.25em 0; }
    .body a { color: #0b57d0; }
    .body code {
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 0.88em;
      background: #f3f3f3;
      padding: 0.1em 0.35em;
      border-radius: 3px;
    }
    .body pre {
      background: #f5f5f5;
      padding: 0.75rem 0.9rem;
      overflow-x: auto;
      border-radius: 4px;
    }
    .body pre code { background: transparent; padding: 0; }
    .body blockquote {
      margin: 0.85em 0;
      padding: 0.15em 0 0.15em 0.9em;
      border-left: 3px solid #ccc;
      color: #444;
    }
    .body table {
      border-collapse: collapse;
      width: 100%;
      margin: 0.85em 0;
      font-size: 0.92em;
    }
    .body th, .body td {
      border: 1px solid #ccc;
      padding: 0.35em 0.55em;
      text-align: left;
    }
    .body th { background: #f3f3f3; }
    .body hr {
      border: none;
      border-top: 1px solid #ddd;
      margin: 1.4em 0;
    }
    @media print {
      body { padding: 0; }
      a { color: inherit; text-decoration: none; }
    }
  </style>
</head>
<body>
  <header>
    <h1>${title}</h1>
    ${subtitle}
    ${meta}
  </header>
  <main class="body">
    ${options.bodyHtml}
  </main>
</body>
</html>`;
}

/**
 * Open the feedback in a new window and invoke the print dialog (Save as PDF).
 *
 * @throws if the browser blocks the pop-up
 */
export function openBacktestFeedbackPrintView(
  options: BacktestFeedbackPrintOptions,
): void {
  const html = buildBacktestFeedbackPrintDocument(options);
  const win = window.open("", "_blank", "noopener,noreferrer");
  if (!win) {
    throw new Error(
      "Pop-up blocked. Allow pop-ups for this site to export PDF.",
    );
  }
  win.document.open();
  win.document.write(html);
  win.document.close();

  const triggerPrint = () => {
    try {
      win.focus();
      win.print();
    } catch {
      /* user can still print manually from the opened tab */
    }
  };

  // Give the new document a tick to finish layout before printing.
  if (win.document.readyState === "complete") {
    window.setTimeout(triggerPrint, 50);
  } else {
    win.addEventListener("load", () => window.setTimeout(triggerPrint, 50), {
      once: true,
    });
  }
}
