import { Outlet } from "react-router-dom";
import { useEffect, useState } from "react";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { api } from "../api/client";
import Sidebar from "./Sidebar";

export default function AppLayout() {
  const [username, setUsername] = useState("");
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem("sidebarCollapsed") === "true",
  );

  useEffect(() => {
    api.me().then((u) => setUsername(u.username)).catch(() => setUsername(""));
  }, []);

  function toggleSidebar() {
    setCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem("sidebarCollapsed", String(next));
      return next;
    });
  }

  async function logout() {
    await api.logout();
    window.location.href = "/login";
  }

  return (
    <div className={`app-shell${collapsed ? " sidebar-collapsed" : ""}`}>
      <Sidebar collapsed={collapsed} />
      <div className="app-main">
        <header className="topbar">
          <button
            type="button"
            className="menu-btn"
            onClick={toggleSidebar}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-expanded={!collapsed}
          >
            {collapsed ? (
              <PanelLeftOpen size={20} strokeWidth={1.75} />
            ) : (
              <PanelLeftClose size={20} strokeWidth={1.75} />
            )}
          </button>
          <div className="topbar-actions">
            <span className="topbar-user">{username}</span>
            <button className="btn btn-sm" type="button" onClick={logout}>
              Logout
            </button>
          </div>
        </header>
        <main className="main-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
