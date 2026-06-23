import { NavLink } from "react-router-dom";
import { useState } from "react";

const NAV_ITEMS = [
  { to: "/", label: "Dashboard", icon: "▣" },
];

export default function Sidebar() {
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem("sidebarCollapsed") === "true",
  );

  function toggle() {
    const next = !collapsed;
    setCollapsed(next);
    localStorage.setItem("sidebarCollapsed", String(next));
  }

  return (
    <aside className={`sidebar${collapsed ? " collapsed" : ""}`}>
      <nav className="sidebar-nav">
        <button
          type="button"
          className="nav-item"
          onClick={toggle}
          title={collapsed ? "Expand" : "Collapse"}
        >
          <span className="nav-icon">{collapsed ? "»" : "«"}</span>
          {!collapsed && <span>Collapse</span>}
        </button>
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end
            className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}
            title={item.label}
          >
            <span className="nav-icon">{item.icon}</span>
            {!collapsed && <span>{item.label}</span>}
          </NavLink>
        ))}
      </nav>
      <div className="sidebar-bottom">
        <NavLink
          to="/settings/general"
          className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}
          title="Settings"
        >
          <span className="nav-icon">⚙</span>
          {!collapsed && <span>Settings</span>}
        </NavLink>
      </div>
    </aside>
  );
}
