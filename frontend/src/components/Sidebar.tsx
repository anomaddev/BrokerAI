import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import type { LucideIcon } from "lucide-react";
import {
  Activity,
  BarChart3,
  CalendarClock,
  Coins,
  Compass,
  Database,
  FileText,
  Gem,
  History,
  LayoutDashboard,
  Layers,
  LineChart,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  TrendingUp,
  Zap,
} from "lucide-react";
import { api, type AssetClass } from "../api/client";
import { useAssetClassStatuses } from "../hooks/useAssetClassStatuses";
import { ROUTES } from "../lib/routes";

type NavItem = {
  to?: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
  disabled?: boolean;
  assetClass?: AssetClass;
};

type ExternalNavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
};

const NAV_ITEMS: NavItem[] = [
  { to: ROUTES.dashboard, label: "Dashboard", icon: LayoutDashboard, end: true },
];

type NavSection = {
  label: string;
  items: NavItem[];
};

const NAV_SECTIONS: NavSection[] = [
  {
    label: "Research & Analysis",
    items: [
      { to: ROUTES.research.reports, label: "Reports", icon: FileText },
      { to: ROUTES.research.strategies, label: "Strategies", icon: LineChart },
      { to: ROUTES.research.analysis, label: "Analysis", icon: Zap },
      { to: ROUTES.research.backtest, label: "Backtest", icon: History },
    ],
  },
  {
    label: "Trading",
    items: [
      { to: ROUTES.trading.explore, label: "Explore", icon: Compass },
      { to: ROUTES.trading.forex, label: "Forex", icon: TrendingUp, assetClass: "forex" },
      { to: undefined, label: "Metals", icon: Gem, disabled: true, assetClass: "metals" },
      { to: undefined, label: "Stocks", icon: BarChart3, disabled: true, assetClass: "stocks" },
      { to: undefined, label: "Options", icon: Layers, disabled: true, assetClass: "options" },
      { to: undefined, label: "Futures", icon: CalendarClock, disabled: true, assetClass: "futures" },
      { to: undefined, label: "Crypto", icon: Coins, disabled: true, assetClass: "crypto" },
    ],
  },
];

const SYSTEM_ITEMS: NavItem[] = [
  { to: ROUTES.activity, label: "Activity", icon: Activity },
  { to: ROUTES.settings, label: "Settings", icon: Settings },
];

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
  onToggle: () => void;
};

function NavStatusDot({ enabled }: { enabled: boolean }) {
  return (
    <span
      className={`nav-status-dot${enabled ? " nav-status-dot--enabled" : " nav-status-dot--disabled"}`}
      aria-hidden="true"
      title={enabled ? "Enabled" : "Disabled"}
    />
  );
}

function NavItemContent({
  item,
  assetClassEnabled,
}: {
  item: NavItem;
  assetClassEnabled?: boolean;
}) {
  const Icon = item.icon;
  const showStatus = item.assetClass != null && assetClassEnabled !== undefined;

  return (
    <>
      <span className="nav-icon" aria-hidden>
        <Icon size={20} strokeWidth={1.75} />
      </span>
      <span className="nav-label">{item.label}</span>
      {showStatus ? <NavStatusDot enabled={assetClassEnabled} /> : null}
    </>
  );
}

function NavItemLink({
  item,
  collapsed,
  assetClassEnabled,
}: {
  item: NavItem;
  collapsed: boolean;
  assetClassEnabled?: boolean;
}) {
  const title = collapsed
    ? item.label
    : item.disabled
      ? "Coming soon"
      : assetClassEnabled != null
        ? `${item.label} (${assetClassEnabled ? "Enabled" : "Disabled"})`
        : undefined;

  if (item.disabled || !item.to) {
    return (
      <span className="nav-item nav-item--disabled" title={title} aria-disabled="true">
        <NavItemContent item={item} assetClassEnabled={assetClassEnabled} />
      </span>
    );
  }

  return (
    <NavLink
      to={item.to}
      end={item.end}
      className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}
      title={title}
    >
      <NavItemContent item={item} assetClassEnabled={assetClassEnabled} />
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

export default function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const assetClassStatuses = useAssetClassStatuses();
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

  function resolveAssetClassEnabled(item: NavItem): boolean | undefined {
    if (!item.assetClass) return undefined;
    if (!(item.assetClass in assetClassStatuses)) return undefined;
    return Boolean(assetClassStatuses[item.assetClass]);
  }

  return (
    <aside className={`sidebar${collapsed ? " collapsed" : ""}`}>
      <div className="sidebar-header">
        {collapsed ? (
          <button
            type="button"
            className="sidebar-toggle-btn"
            onClick={onToggle}
            aria-label="Expand sidebar"
            aria-expanded={false}
          >
            <PanelLeftOpen size={20} strokeWidth={1.75} />
          </button>
        ) : (
          <>
            <span className="sidebar-brand-icon" aria-hidden>
              <TrendingUp size={22} strokeWidth={2} />
            </span>
            <span className="sidebar-title">BrokerAI</span>
            <button
              type="button"
              className="sidebar-toggle-btn sidebar-toggle-btn--collapse"
              onClick={onToggle}
              aria-label="Collapse sidebar"
              aria-expanded
            >
              <PanelLeftClose size={18} strokeWidth={1.75} />
            </button>
          </>
        )}
      </div>
      <nav className="sidebar-nav" aria-label="Main">
        {NAV_ITEMS.map((item) => (
          <NavItemLink
            key={item.label}
            item={item}
            collapsed={collapsed}
            assetClassEnabled={resolveAssetClassEnabled(item)}
          />
        ))}
        {NAV_SECTIONS.map((section) => (
          <div key={section.label} className="sidebar-nav-section">
            <span className="sidebar-section-label">{section.label}</span>
            {section.items.map((item) => (
              <NavItemLink
                key={item.label}
                item={item}
                collapsed={collapsed}
                assetClassEnabled={resolveAssetClassEnabled(item)}
              />
            ))}
          </div>
        ))}
      </nav>
      <div className="sidebar-advanced">
        <span className="sidebar-section-label">External</span>
        {advancedItems.map((item) => (
          <ExternalNavItemLink key={item.label} item={item} collapsed={collapsed} />
        ))}
      </div>
      <div className="sidebar-bottom">
        <span className="sidebar-section-label">System</span>
        {SYSTEM_ITEMS.map((item) => (
          <NavItemLink
            key={item.label}
            item={item}
            collapsed={collapsed}
            assetClassEnabled={resolveAssetClassEnabled(item)}
          />
        ))}
        <div className="sidebar-bottom-spacer" aria-hidden="true" />
      </div>
    </aside>
  );
}
