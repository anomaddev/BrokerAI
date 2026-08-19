import { Outlet, useLocation } from "react-router-dom";
import { useEffect, useState } from "react";
import { Menu } from "lucide-react";
import Sidebar from "./Sidebar";
import MarketSessionsBar from "./MarketSessionsBar";
import OverallBotStatus from "./OverallBotStatus";
import TaskProgressFooter from "./TaskProgressFooter";
import { UserMenuContainer } from "./UserMenu";
import { BackgroundTasksProvider, useBackgroundTasks } from "../context/BackgroundTasksContext";
import { useGeneralSettings } from "../hooks/useGeneralSettings";
import { useIsMobile } from "../hooks/useMediaQuery";

type AppMainProps = {
  isMobile: boolean;
  onOpenMobileNav: () => void;
};

function AppMain({ isMobile, onOpenMobileNav }: AppMainProps) {
  const { activeTask, recentTask } = useBackgroundTasks();
  useGeneralSettings();
  const showFooter = Boolean(activeTask || recentTask);

  return (
    <div className={`app-main${showFooter ? " app-main--task-footer" : ""}`}>
      <header className="topbar">
        <div className="topbar-start">
          {isMobile ? (
            <button
              type="button"
              className="topbar-menu-btn"
              onClick={onOpenMobileNav}
              aria-label="Open navigation menu"
            >
              <Menu size={22} strokeWidth={1.75} aria-hidden />
            </button>
          ) : null}
          <OverallBotStatus />
        </div>
        <div className="topbar-actions">
          {!isMobile ? <MarketSessionsBar /> : null}
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
  const isMobile = useIsMobile();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem("sidebarCollapsed") === "true",
  );
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  function toggleSidebar() {
    setCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem("sidebarCollapsed", String(next));
      return next;
    });
  }

  function closeMobileNav() {
    setMobileNavOpen(false);
  }

  // Close the drawer on navigation so the destination page is fully visible.
  useEffect(() => {
    setMobileNavOpen(false);
  }, [location.pathname, location.search]);

  // Escape closes the drawer; ignore when closed.
  useEffect(() => {
    if (!mobileNavOpen) return;

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setMobileNavOpen(false);
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [mobileNavOpen]);

  // Lock background scroll while the drawer is open (mobile only).
  useEffect(() => {
    if (!isMobile || !mobileNavOpen) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [isMobile, mobileNavOpen]);

  // Leaving mobile should never leave the drawer state hanging.
  useEffect(() => {
    if (!isMobile) {
      setMobileNavOpen(false);
    }
  }, [isMobile]);

  return (
    <BackgroundTasksProvider>
      <div
        className={`app-shell${collapsed && !isMobile ? " sidebar-collapsed" : ""}${
          isMobile ? " app-shell--mobile" : ""
        }${mobileNavOpen ? " mobile-nav-open" : ""}`}
      >
        {isMobile && mobileNavOpen ? (
          <button
            type="button"
            className="sidebar-scrim"
            aria-label="Close navigation menu"
            onClick={closeMobileNav}
          />
        ) : null}
        <Sidebar
          variant={isMobile ? "drawer" : "rail"}
          collapsed={!isMobile && collapsed}
          open={isMobile ? mobileNavOpen : true}
          onToggle={toggleSidebar}
          onNavigate={isMobile ? closeMobileNav : undefined}
        />
        <AppMain isMobile={isMobile} onOpenMobileNav={() => setMobileNavOpen(true)} />
      </div>
    </BackgroundTasksProvider>
  );
}
