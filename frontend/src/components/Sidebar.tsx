import { NavLink, useLocation } from "react-router-dom";
import type { LucideIcon } from "lucide-react";
import {
  Activity,
  BarChart3,
  Brain,
  CalendarClock,
  CircleDollarSign,
  Coins,
  Compass,
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
import type { AssetClass } from "../api/client";
import { useAssetClassStatuses } from "../hooks/useAssetClassStatuses";
import { useResearchReportsUnreadCount } from "../hooks/useResearchReportsUnreadCount";
import { ROUTES } from "../lib/routes";

type NavItem = {
  to?: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
  disabled?: boolean;
  assetClass?: AssetClass;
  badge?: number;
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
      { to: ROUTES.research.aiStrategies, label: "AI Strategies", icon: Brain },
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
  { to: ROUTES.costLedger, label: "Cost Ledger", icon: CircleDollarSign },
  { to: ROUTES.settings, label: "Settings", icon: Settings },
];

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

function NavCountBadge({ count }: { count: number }) {
  if (count <= 0) return null;
  const label = count > 99 ? "99+" : String(count);
  return (
    <span className="nav-count-badge" aria-label={`${count} unread`}>
      {label}
    </span>
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
  const badge = item.badge ?? 0;

  return (
    <>
      <span className="nav-icon" aria-hidden>
        <Icon size={20} strokeWidth={1.75} />
      </span>
      <span className="nav-label">{item.label}</span>
      {showStatus ? <NavStatusDot enabled={assetClassEnabled} /> : null}
      {!showStatus ? <NavCountBadge count={badge} /> : null}
    </>
  );
}

function isNavItemPathActive(
  pathname: string,
  search: string,
  to: string,
  end?: boolean,
): boolean {
  const [pathOnly, query = ""] = to.split("?");
  if (end) {
    return pathname === pathOnly;
  }
  if (!(pathname === pathOnly || pathname.startsWith(`${pathOnly}/`))) {
    return false;
  }
  if (!query) {
    return true;
  }
  const wanted = new URLSearchParams(query);
  const current = new URLSearchParams(search);
  for (const [key, value] of wanted.entries()) {
    if (current.get(key) !== value) return false;
  }
  return true;
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
  const location = useLocation();
  const title = collapsed
    ? item.badge && item.badge > 0
      ? `${item.label} (${item.badge} unread)`
      : item.label
    : item.disabled
      ? "Coming soon"
      : assetClassEnabled != null
        ? `${item.label} (${assetClassEnabled ? "Enabled" : "Disabled"})`
        : item.badge && item.badge > 0
          ? `${item.label} (${item.badge} unread)`
          : undefined;

  if (item.disabled || !item.to) {
    return (
      <span className="nav-item nav-item--disabled" title={title} aria-disabled="true">
        <NavItemContent item={item} assetClassEnabled={assetClassEnabled} />
      </span>
    );
  }

  const active = isNavItemPathActive(
    location.pathname,
    location.search,
    item.to,
    item.end,
  );

  return (
    <NavLink
      to={item.to}
      className={`nav-item${active ? " active" : ""}`}
      title={title}
    >
      <NavItemContent item={item} assetClassEnabled={assetClassEnabled} />
    </NavLink>
  );
}

export default function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const assetClassStatuses = useAssetClassStatuses();
  const unread = useResearchReportsUnreadCount();

  function resolveAssetClassEnabled(item: NavItem): boolean | undefined {
    if (!item.assetClass) return undefined;
    if (!(item.assetClass in assetClassStatuses)) return undefined;
    return Boolean(assetClassStatuses[item.assetClass]);
  }

  function withUnreadBadge(item: NavItem): NavItem {
    if (item.to === ROUTES.research.reports) {
      return { ...item, badge: unread.unread_count };
    }
    return item;
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
            {section.items.map((item) => {
              const navItem = withUnreadBadge(item);
              return (
                <NavItemLink
                  key={item.label}
                  item={navItem}
                  collapsed={collapsed}
                  assetClassEnabled={resolveAssetClassEnabled(navItem)}
                />
              );
            })}
          </div>
        ))}
      </nav>
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
