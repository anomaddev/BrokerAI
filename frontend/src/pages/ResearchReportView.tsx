import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, type ResearchReportContent } from "../api/client";
import { ROUTES } from "../lib/routes";
import { useGeneralSettings } from "../hooks/useGeneralSettings";

const TYPE_LABELS: Record<string, string> = {
  daily: "Daily report",
  daily_model: "Per-model report",
  weekly_brief: "Weekly brief",
  weekly_debrief: "Weekly debrief",
};

function reportTitle(report: ResearchReportContent): string {
  const typeLabel = report.type ? TYPE_LABELS[report.type] ?? report.type : "Report";
  const parts = [typeLabel];
  if (report.model_label) parts.push(report.model_label);
  if (report.date) parts.push(report.date);
  return parts.join(" · ");
}

export default function ResearchReportView() {
  const { formatInstant } = useGeneralSettings();
  const params = useParams();
  const filename = params["*"] ?? "";
  const [report, setReport] = useState<ResearchReportContent | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showRaw, setShowRaw] = useState(false);

  useEffect(() => {
    if (!filename) {
      setError("No report specified");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    api
      .getResearchReport(filename)
      .then((data) => setReport(data))
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Failed to load report"),
      )
      .finally(() => setLoading(false));
  }, [filename]);

  return (
    <div>
      <div className="research-view-header">
        <Link to={ROUTES.research.reports} className="research-back-link">
          <ArrowLeft size={16} strokeWidth={1.75} />
          Back to reports
        </Link>
        {report && (
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => setShowRaw((prev) => !prev)}
          >
            {showRaw ? "Rendered" : "Raw markdown"}
          </button>
        )}
      </div>

      {loading && <p className="settings-muted">Loading report…</p>}
      {error && !loading && <p className="settings-error">{error}</p>}

      {report && !loading && !error && (
        <article className="settings-panel">
          <h1 className="page-title" style={{ marginBottom: "0.25rem" }}>
            {reportTitle(report)}
          </h1>
          <p className="settings-muted" style={{ marginBottom: "1rem" }}>
            {report.filename}
            {report.generated_at
              ? ` · Generated ${formatInstant(report.generated_at, "short")}`
              : ""}
          </p>
          {showRaw ? (
            <pre className="research-report-raw">{report.content}</pre>
          ) : (
            <div className="research-report-body">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{report.content}</ReactMarkdown>
            </div>
          )}
        </article>
      )}
    </div>
  );
}
