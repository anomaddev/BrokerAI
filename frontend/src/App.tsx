import { Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { useEffect, useState } from "react";
import { api } from "./api/client";
import Setup from "./pages/Setup";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
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
  }, [location.pathname]);

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
          <Route path="/settings/*" element={<Settings />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthGate>
  );
}
