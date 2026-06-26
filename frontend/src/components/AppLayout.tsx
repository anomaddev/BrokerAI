import { Outlet } from "react-router-dom";
import { useState } from "react";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import Sidebar from "./Sidebar";
import { UserMenuContainer } from "./UserMenu";

export default function AppLayout() {
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem("sidebarCollapsed") === "true",
  );

  function toggleSidebar() {
    setCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem("sidebarCollapsed", String(next));
      return next;
    });
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
            <UserMenuContainer />
          </div>
        </header>
        <main className="main-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
