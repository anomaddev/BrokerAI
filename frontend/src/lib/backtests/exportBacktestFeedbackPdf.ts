/**
 * Download AI backtest feedback as a PDF (no pop-up / print dialog).
 */

import html2canvas from "html2canvas";
import { jsPDF } from "jspdf";

export type BacktestFeedbackPrintOptions = {
  title: string;
  subtitle?: string;
  metaLines?: string[];
  /** Sanitized HTML from the already-rendered markdown body. */
  bodyHtml: string;
  /** Optional download basename without extension. */
  filename?: string;
};

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function sanitizeFilename(value: string): string {
  const cleaned = value
    .trim()
    .replace(/[^\w\s.-]+/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
  return cleaned || "ai-feedback";
}

/** Build the standalone HTML document used for PDF rendering. */
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

function mountOfflineDocument(html: string): HTMLIFrameElement {
  const iframe = document.createElement("iframe");
  iframe.setAttribute("aria-hidden", "true");
  iframe.style.position = "fixed";
  iframe.style.left = "-10000px";
  iframe.style.top = "0";
  iframe.style.width = "820px";
  iframe.style.height = "1160px";
  iframe.style.border = "0";
  iframe.style.opacity = "0";
  iframe.style.pointerEvents = "none";
  document.body.appendChild(iframe);

  const doc = iframe.contentDocument;
  if (!doc) {
    iframe.remove();
    throw new Error("Failed to create PDF renderer");
  }
  doc.open();
  doc.write(html);
  doc.close();
  return iframe;
}

function waitForIframeLoad(iframe: HTMLIFrameElement): Promise<void> {
  return new Promise((resolve) => {
    const done = () => resolve();
    if (iframe.contentDocument?.readyState === "complete") {
      window.setTimeout(done, 50);
      return;
    }
    iframe.addEventListener(
      "load",
      () => {
        window.setTimeout(done, 50);
      },
      { once: true },
    );
  });
}

/**
 * Render feedback HTML to a multi-page PDF and trigger a normal file download.
 */
export async function downloadBacktestFeedbackPdf(
  options: BacktestFeedbackPrintOptions,
): Promise<void> {
  const html = buildBacktestFeedbackPrintDocument(options);
  const filename = `${sanitizeFilename(options.filename || options.title)}.pdf`;
  const iframe = mountOfflineDocument(html);

  try {
    await waitForIframeLoad(iframe);
    const source = iframe.contentDocument?.body;
    if (!source) {
      throw new Error("Failed to render feedback for PDF export");
    }

    const canvas = await html2canvas(source, {
      scale: 2,
      useCORS: true,
      logging: false,
      backgroundColor: "#ffffff",
      windowWidth: 820,
    });

    const pdf = new jsPDF({
      orientation: "portrait",
      unit: "pt",
      format: "a4",
    });
    const pageWidth = pdf.internal.pageSize.getWidth();
    const pageHeight = pdf.internal.pageSize.getHeight();
    const margin = 36;
    const contentWidth = pageWidth - margin * 2;
    const contentHeight = pageHeight - margin * 2;

    const imgWidth = contentWidth;
    const imgHeight = (canvas.height * imgWidth) / canvas.width;
    const pageCanvas = document.createElement("canvas");
    const pageCtx = pageCanvas.getContext("2d");
    if (!pageCtx) {
      throw new Error("Failed to slice PDF pages");
    }

    const pxPerPt = canvas.width / imgWidth;
    const pageHeightPx = contentHeight * pxPerPt;
    let renderedHeight = 0;
    let pageIndex = 0;

    while (renderedHeight < canvas.height) {
      const sliceHeight = Math.min(pageHeightPx, canvas.height - renderedHeight);
      pageCanvas.width = canvas.width;
      pageCanvas.height = Math.max(1, Math.floor(sliceHeight));
      pageCtx.fillStyle = "#ffffff";
      pageCtx.fillRect(0, 0, pageCanvas.width, pageCanvas.height);
      pageCtx.drawImage(
        canvas,
        0,
        renderedHeight,
        canvas.width,
        sliceHeight,
        0,
        0,
        canvas.width,
        sliceHeight,
      );

      const pageData = pageCanvas.toDataURL("image/jpeg", 0.92);
      if (pageIndex > 0) pdf.addPage();
      pdf.addImage(
        pageData,
        "JPEG",
        margin,
        margin,
        imgWidth,
        sliceHeight / pxPerPt,
      );

      renderedHeight += sliceHeight;
      pageIndex += 1;
    }

    pdf.save(filename);
  } finally {
    iframe.remove();
  }
}
