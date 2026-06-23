import { NavLink } from "react-router-dom";

const NAV_ITEMS = [
  { to: "/", label: "Dashboard", icon: "▣" },
];

type SidebarProps = {
  open: boolean;
  onClose: () => void;
};

export default function Sidebar({ open, onClose }: SidebarProps) {
  return (
    <>
      <div
        className={`sidebar-backdrop${open ? " visible" : ""}`}
        onClick={onClose}
        aria-hidden={!open}
      />
      <aside className={`sidebar${open ? " open" : ""}`} aria-hidden={!open}>
        <div className="sidebar-header">
          <span className="sidebar-title">BrokerAI</span>
        </div>
        <nav className="sidebar-nav">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end
              className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}
              onClick={onClose}
            >
              <span className="nav-icon">{item.icon}</span>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <NavLink
            to="/settings/general"
            className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}
            onClick={onClose}
          >
            <span className="nav-icon">⚙</span>
            <span>Settings</span>
          </NavLink>
        </div>
      </aside>
    </>
  );
}
