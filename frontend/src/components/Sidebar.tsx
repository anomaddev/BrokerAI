import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import type { LucideIcon } from "lucide-react";
import { Database, LayoutDashboard, Search, Settings, TrendingUp } from "lucide-react";
import { api } from "../api/client";

type NavItem = {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
};

type ExternalNavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
};

const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/research", label: "Research", icon: Search },
];

const SETTINGS_ITEM: NavItem = {
  to: "/settings",
  label: "Settings",
  icon: Settings,
};

const DEFAULT_MONGODB_URI = "mongodb://127.0.0.1:27017";
const DEFAULT_DATABASE = "brokerai";

function buildMongoConnectionString(uri: string, database: string): string {
  const base = uri.startsWith("mongodb://") || uri.startsWith("mongodb+srv://")
    ? uri.replace(/\/$/, "")
    : `mongodb://${uri.replace(/\/$/, "")}`;
  return `${base}/${database}`;
}

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

function ExternalNavItemLink({ item, collapsed }: { item: ExternalNavItem; collapsed: boolean }) {
  const Icon = item.icon;
  return (
    <a
      href={item.href}
      className="nav-item"
      title={collapsed ? item.label : undefined}
    >
      <span className="nav-icon" aria-hidden>
        <Icon size={20} strokeWidth={1.75} />
      </span>
      <span className="nav-label">{item.label}</span>
    </a>
  );
}

export default function Sidebar({ collapsed }: SidebarProps) {
  const [mongoConnection, setMongoConnection] = useState(
    buildMongoConnectionString(DEFAULT_MONGODB_URI, DEFAULT_DATABASE),
  );

  useEffect(() => {
    api
      .dbStats()
      .then((db) => {
        const uri = typeof db.uri === "string" && db.uri ? db.uri : DEFAULT_MONGODB_URI;
        const database =
          typeof db.database === "string" && db.database ? db.database : DEFAULT_DATABASE;
        setMongoConnection(buildMongoConnectionString(uri, database));
      })
      .catch(() => {
        setMongoConnection(buildMongoConnectionString(DEFAULT_MONGODB_URI, DEFAULT_DATABASE));
      });
  }, []);

  const advancedItems: ExternalNavItem[] = [
    { href: mongoConnection, label: "MongoDB Compass", icon: Database },
  ];

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
      <div className="sidebar-advanced">
        <span className="sidebar-section-label">Advanced</span>
        {advancedItems.map((item) => (
          <ExternalNavItemLink key={item.label} item={item} collapsed={collapsed} />
        ))}
      </div>
      <div className="sidebar-bottom">
        <NavItemLink item={SETTINGS_ITEM} collapsed={collapsed} />
      </div>
    </aside>
  );
}
