import { NavLink } from "react-router-dom";
import type { LucideIcon } from "lucide-react";
import { LayoutDashboard, Settings, TrendingUp } from "lucide-react";

type NavItem = {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
};

const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
];

const SETTINGS_ITEM: NavItem = {
  to: "/settings/general",
  label: "Settings",
  icon: Settings,
};

type SidebarProps = {
  collapsed: boolean;
};

function NavItemLink({ item, collapsed }: { item: NavItem; collapsed: boolean }) {
  const Icon = item.icon;
  return (
    <NavLink
      to={item.to}
      end={item.end}
      className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}
      title={collapsed ? item.label : undefined}
    >
      <span className="nav-icon" aria-hidden>
        <Icon size={20} strokeWidth={1.75} />
      </span>
      <span className="nav-label">{item.label}</span>
    </NavLink>
  );
}

export default function Sidebar({ collapsed }: SidebarProps) {
  return (
    <aside className={`sidebar${collapsed ? " collapsed" : ""}`}>
      <div className="sidebar-header">
        <span className="sidebar-brand-icon" aria-hidden>
          <TrendingUp size={22} strokeWidth={2} />
        </span>
        <span className="sidebar-title">BrokerAI</span>
      </div>
      <nav className="sidebar-nav" aria-label="Main">
        {NAV_ITEMS.map((item) => (
          <NavItemLink key={item.to} item={item} collapsed={collapsed} />
        ))}
      </nav>
      <div className="sidebar-bottom">
        <NavItemLink item={SETTINGS_ITEM} collapsed={collapsed} />
      </div>
    </aside>
  );
}
