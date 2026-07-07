import { Navigate, Route, Routes, useLocation, useParams } from "react-router-dom";
import { useEffect, useState } from "react";
import { api } from "./api/client";
import Setup from "./pages/Setup";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Research from "./pages/Research";
import ResearchReportView from "./pages/ResearchReportView";
import Strategies from "./pages/Strategies";
import Explore from "./pages/Explore";
import Backtesting from "./pages/Backtesting";
import StrategyBuilderPage from "./pages/strategies/StrategyBuilderPage";
import StrategyEditPage from "./pages/strategies/StrategyEditPage";
import Activity from "./pages/Activity";
import CostLedger from "./pages/CostLedger";
import StrategyAnalysis from "./pages/StrategyAnalysis";
import StrategyAnalysisCandleView from "./pages/StrategyAnalysisCandleView";
import StrategyAnalysisRunView from "./pages/StrategyAnalysisRunView";
import Trades from "./pages/Trades";
import Settings from "./pages/Settings";
import AppLayout from "./components/AppLayout";
import { ROUTES } from "./lib/routes";

function LegacyReportRedirect() {
  const params = useParams();
  const suffix = params["*"] ?? "";
  return <Navigate to={`/research/reports/r/${suffix}`} replace />;
}

function LegacyAnalysisRunRedirect() {
  const { runId } = useParams();
  if (!runId) {
    return <Navigate to={ROUTES.research.analysis} replace />;
  }
  return <Navigate to={ROUTES.research.analysisRun(runId)} replace />;
}

function LegacyAnalysisRunFlatRedirect() {
  const { runId } = useParams();
  if (!runId) {
    return <Navigate to={ROUTES.research.analysis} replace />;
  }
  return <Navigate to={ROUTES.research.analysisRun(runId)} replace />;
}

function LegacyStrategyNewRedirect() {
  const { presetId } = useParams();
  return <Navigate to={`/research/strategies/new/${presetId ?? ""}`} replace />;
}

function LegacyStrategyEditRedirect() {
  const { id } = useParams();
  return <Navigate to={`/research/strategies/${id ?? ""}/edit`} replace />;
}

type AuthStatus = "loading" | "setup" | "auth" | "oidc" | "ok";

function AuthGate({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const location = useLocation();

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const config = await api.authConfig();
        if (cancelled) return;

        if (config.mode === "oidc") {
          try {
            await api.me();
            if (!cancelled) setStatus("ok");
          } catch {
            if (!cancelled) setStatus("oidc");
          }
          return;
        }

        const { setup_complete } = await api.setupStatus();
        if (cancelled) return;
        if (!setup_complete) {
          setStatus("setup");
          return;
        }
        await api.me();
        if (!cancelled) setStatus("ok");
      } catch {
        if (!cancelled) setStatus("auth");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (status === "loading") {
    return <div className="center-page">Loading…</div>;
  }

  if (status === "oidc") {
    window.location.href = "/api/auth/oidc/login";
    return <div className="center-page">Redirecting to sign in…</div>;
  }

  if (status === "setup" && location.pathname !== "/setup") {
    return <Navigate to="/setup" replace />;
  }
  if (status === "auth" && !["/login", "/setup"].includes(location.pathname)) {
    return <Navigate to="/login" replace />;
  }
  if (status === "ok" && ["/login", "/setup"].includes(location.pathname)) {
    return <Navigate to="/" replace />;
  }

  return (
    <>
      {children}
    </>
  );
}

export default function App() {
  return (
    <AuthGate>
      <Routes>
        <Route path="/setup" element={<Setup />} />
        <Route path="/login" element={<Login />} />
        <Route element={<AppLayout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/research/reports" element={<Research />} />
          <Route path="/research/reports/r/*" element={<ResearchReportView />} />
          <Route path="/research/strategies" element={<Strategies />} />
          <Route path="/research/strategies/new/:presetId" element={<StrategyBuilderPage />} />
          <Route path="/research/strategies/:id/edit" element={<StrategyEditPage />} />
          <Route path="/research/analysis" element={<StrategyAnalysis />} />
          <Route
            path="/research/analysis/candle/:candleKey"
            element={<StrategyAnalysisCandleView />}
          />
          <Route path="/research/analysis/run/:runId" element={<StrategyAnalysisRunView />} />
          <Route
            path="/research/analysis/:runId"
            element={<LegacyAnalysisRunFlatRedirect />}
          />
          <Route path="/research/backtest" element={<Backtesting />} />
          <Route path="/trading/forex" element={<Trades />} />
          <Route path="/trading/explore" element={<Explore />} />
          <Route path="/activity" element={<Activity />} />
          <Route path="/cost-ledger" element={<CostLedger />} />
          <Route path="/settings/*" element={<Settings />} />
          <Route path="/daily-reports" element={<Navigate to="/research/reports" replace />} />
          <Route path="/daily-reports/r/*" element={<LegacyReportRedirect />} />
          <Route path="/trading/strategies" element={<Navigate to="/research/strategies" replace />} />
          <Route path="/trading/strategies/new/:presetId" element={<LegacyStrategyNewRedirect />} />
          <Route path="/trading/strategies/:id/edit" element={<LegacyStrategyEditRedirect />} />
          <Route path="/trading/analysis" element={<Navigate to="/research/analysis" replace />} />
          <Route path="/trading/analysis/:runId" element={<LegacyAnalysisRunRedirect />} />
          <Route path="/research/backtesting" element={<Navigate to="/research/backtest" replace />} />
          <Route path="/trading/trades" element={<Navigate to="/trading/forex" replace />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthGate>
  );
}
