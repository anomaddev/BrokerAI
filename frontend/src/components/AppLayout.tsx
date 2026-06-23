import { Outlet } from "react-router-dom";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import Sidebar from "./Sidebar";

export default function AppLayout() {
  const [username, setUsername] = useState("");
  const [menuOpen, setMenuOpen] = useState(
    () => localStorage.getItem("sidebarOpen") !== "false",
  );

  useEffect(() => {
    api.me().then((u) => setUsername(u.username)).catch(() => setUsername(""));
  }, []);

  function toggleMenu() {
    setMenuOpen((prev) => {
      const next = !prev;
      localStorage.setItem("sidebarOpen", String(next));
      return next;
    });
  }

  function closeMenu() {
    setMenuOpen(false);
    localStorage.setItem("sidebarOpen", "false");
  }

  async function logout() {
    await api.logout();
    window.location.href = "/login";
  }

  return (
    <div className={`app-shell${menuOpen ? " menu-open" : ""}`}>
      <Sidebar open={menuOpen} onClose={closeMenu} />
      <div className="app-main">
        <header className="topbar">
          <button
            type="button"
            className="menu-btn"
            onClick={toggleMenu}
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            aria-expanded={menuOpen}
          >
            <span className="menu-btn-bar" />
            <span className="menu-btn-bar" />
            <span className="menu-btn-bar" />
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
