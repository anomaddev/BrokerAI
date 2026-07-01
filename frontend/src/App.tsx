import { Navigate, Route, Routes, useLocation } from "react-router-dom";
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
import StrategyAnalysis from "./pages/StrategyAnalysis";
import StrategyAnalysisRunView from "./pages/StrategyAnalysisRunView";
import Trades from "./pages/Trades";
import Settings from "./pages/Settings";
import AppLayout from "./components/AppLayout";

function AuthGate({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<"loading" | "setup" | "auth" | "ok">("loading");
  const location = useLocation();

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
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
  if (status === "setup" && location.pathname !== "/setup") {
    return <Navigate to="/setup" replace />;
  }
  if (status === "auth" && !["/login", "/setup"].includes(location.pathname)) {
    return <Navigate to="/login" replace />;
  }
  if (status === "ok" && ["/login", "/setup"].includes(location.pathname)) {
    return <Navigate to="/" replace />;
  }
  return <>{children}</>;
}

export default function App() {
  return (
    <AuthGate>
      <Routes>
        <Route path="/setup" element={<Setup />} />
        <Route path="/login" element={<Login />} />
        <Route element={<AppLayout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/daily-reports" element={<Research />} />
          <Route path="/daily-reports/r/*" element={<ResearchReportView />} />
          <Route path="/trading/explore" element={<Explore />} />
          <Route path="/research/backtesting" element={<Backtesting />} />
          <Route path="/trading/strategies" element={<Strategies />} />
          <Route path="/trading/strategies/new/:presetId" element={<StrategyBuilderPage />} />
          <Route path="/trading/strategies/:id/edit" element={<StrategyEditPage />} />
          <Route path="/trading/trades" element={<Trades />} />
          <Route path="/trading/analysis" element={<StrategyAnalysis />} />
          <Route path="/trading/analysis/:runId" element={<StrategyAnalysisRunView />} />
          <Route path="/research" element={<Navigate to="/daily-reports" replace />} />
          <Route path="/research/r/*" element={<Navigate to="/daily-reports" replace />} />
          <Route path="/activity" element={<Activity />} />
          <Route path="/settings/*" element={<Settings />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthGate>
  );
}
