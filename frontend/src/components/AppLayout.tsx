import { Outlet } from "react-router-dom";
import { useState } from "react";
import Sidebar from "./Sidebar";
import MarketSessionsBar from "./MarketSessionsBar";
import OverallBotStatus from "./OverallBotStatus";
import TaskProgressFooter from "./TaskProgressFooter";
import { UserMenuContainer } from "./UserMenu";
import { BackgroundTasksProvider, useBackgroundTasks } from "../context/BackgroundTasksContext";
import { useGeneralSettings } from "../hooks/useGeneralSettings";

function AppMain() {
  const { activeTask, recentTask } = useBackgroundTasks();
  useGeneralSettings();
  const showFooter = Boolean(activeTask || recentTask);

  return (
    <div className={`app-main${showFooter ? " app-main--task-footer" : ""}`}>
      <header className="topbar">
        <div className="topbar-start">
          <OverallBotStatus />
        </div>
        <div className="topbar-actions">
          <MarketSessionsBar />
          <UserMenuContainer />
        </div>
      </header>
      <main className="main-content">
        <Outlet />
      </main>
      <TaskProgressFooter />
    </div>
  );
}

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
    <BackgroundTasksProvider>
      <div className={`app-shell${collapsed ? " sidebar-collapsed" : ""}`}>
        <Sidebar collapsed={collapsed} onToggle={toggleSidebar} />
        <AppMain />
      </div>
    </BackgroundTasksProvider>
  );
}
