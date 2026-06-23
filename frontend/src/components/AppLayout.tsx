import { NavLink, Outlet } from "react-router-dom";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import Sidebar from "./Sidebar";

export default function AppLayout() {
  const [username, setUsername] = useState("");

  useEffect(() => {
    api.me().then((u) => setUsername(u.username)).catch(() => setUsername(""));
  }, []);

  async function logout() {
    await api.logout();
    window.location.href = "/login";
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar-title">BrokerAI</div>
        <div style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
          <span style={{ color: "var(--muted)", fontSize: "0.875rem" }}>{username}</span>
          <button className="btn" type="button" onClick={logout} style={{ padding: "0.4rem 0.75rem" }}>
            Logout
          </button>
        </div>
      </header>
      <div className="body-row">
        <Sidebar />
        <main className="main-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
