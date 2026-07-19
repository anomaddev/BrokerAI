import {
  Activity,
  BarChart3,
  Compass,
  LayoutDashboard,
  LineChart,
  Settings,
  TrendingUp,
  Zap,
} from "lucide-react";

/** Decorative app chrome shown blurred behind the setup dialog. */
export default function OnboardingBackdrop() {
  return (
    <div className="onboarding-backdrop" aria-hidden="true">
      <div className="app-shell onboarding-backdrop-shell">
        <aside className="sidebar onboarding-backdrop-sidebar">
          <div className="sidebar-header">
            <span className="sidebar-brand-icon">
              <LayoutDashboard size={16} />
            </span>
            <span className="sidebar-title">BrokerAI</span>
          </div>
          <nav className="sidebar-nav">
            <div className="onboarding-backdrop-nav-item is-active">
              <LayoutDashboard size={16} />
              <span>Dashboard</span>
            </div>
            <p className="sidebar-section-label">Research & Analysis</p>
            <div className="onboarding-backdrop-nav-item">
              <LineChart size={16} />
              <span>Strategies</span>
            </div>
            <div className="onboarding-backdrop-nav-item">
              <Zap size={16} />
              <span>Analysis</span>
            </div>
            <p className="sidebar-section-label">Trading</p>
            <div className="onboarding-backdrop-nav-item">
              <Compass size={16} />
              <span>Explore</span>
            </div>
            <div className="onboarding-backdrop-nav-item">
              <TrendingUp size={16} />
              <span>Forex</span>
            </div>
            <p className="sidebar-section-label">System</p>
            <div className="onboarding-backdrop-nav-item">
              <Activity size={16} />
              <span>Activity</span>
            </div>
            <div className="onboarding-backdrop-nav-item">
              <Settings size={16} />
              <span>Settings</span>
            </div>
          </nav>
        </aside>

        <div className="app-main">
          <header className="topbar onboarding-backdrop-topbar">
            <div className="topbar-start">
              <div className="onboarding-backdrop-pill" />
              <div className="onboarding-backdrop-pill onboarding-backdrop-pill--short" />
              <div className="onboarding-backdrop-pill onboarding-backdrop-pill--short" />
            </div>
            <div className="topbar-actions">
              <div className="onboarding-backdrop-avatar" />
            </div>
          </header>

          <main className="main-content onboarding-backdrop-main">
            <div className="onboarding-backdrop-page-title">
              <h2>Dashboard</h2>
              <p>Account overview</p>
            </div>

            <div className="onboarding-backdrop-stats">
              <div className="onboarding-backdrop-stat">
                <span>Balance</span>
                <strong>$10,000.00</strong>
              </div>
              <div className="onboarding-backdrop-stat">
                <span>Open P&amp;L</span>
                <strong className="is-up">+$128.40</strong>
              </div>
              <div className="onboarding-backdrop-stat">
                <span>Open lots</span>
                <strong>3</strong>
              </div>
              <div className="onboarding-backdrop-stat">
                <span>Strategies</span>
                <strong>2</strong>
              </div>
            </div>

            <div className="onboarding-backdrop-panels">
              <section className="onboarding-backdrop-panel onboarding-backdrop-panel--chart">
                <header>
                  <BarChart3 size={14} />
                  <span>EUR/USD · M15</span>
                </header>
                <div className="onboarding-backdrop-chart">
                  <svg viewBox="0 0 320 120" preserveAspectRatio="none">
                    <polyline
                      fill="none"
                      stroke="var(--accent)"
                      strokeWidth="2"
                      points="0,80 30,72 60,78 90,55 120,62 150,40 180,48 210,28 240,36 270,22 300,30 320,18"
                    />
                    <polyline
                      fill="none"
                      stroke="var(--chart-ema-slow)"
                      strokeWidth="1.5"
                      opacity="0.7"
                      points="0,88 40,82 80,70 120,68 160,52 200,50 240,42 280,38 320,34"
                    />
                  </svg>
                </div>
              </section>

              <section className="onboarding-backdrop-panel">
                <header>
                  <Activity size={14} />
                  <span>Recent activity</span>
                </header>
                <ul className="onboarding-backdrop-list">
                  <li>
                    <span>Pipeline · EUR/USD</span>
                    <em>2m</em>
                  </li>
                  <li>
                    <span>Analysis · GBP/USD</span>
                    <em>8m</em>
                  </li>
                  <li>
                    <span>Broker sync</span>
                    <em>14m</em>
                  </li>
                  <li>
                    <span>Research brief</span>
                    <em>1h</em>
                  </li>
                </ul>
              </section>
            </div>

            <section className="onboarding-backdrop-panel">
              <header>
                <TrendingUp size={14} />
                <span>Open positions</span>
              </header>
              <div className="onboarding-backdrop-table">
                <div>
                  <span>EUR/USD</span>
                  <span className="is-up">Long</span>
                  <span>+0.32%</span>
                </div>
                <div>
                  <span>GBP/USD</span>
                  <span className="is-down">Short</span>
                  <span>-0.11%</span>
                </div>
                <div>
                  <span>USD/JPY</span>
                  <span className="is-up">Long</span>
                  <span>+0.08%</span>
                </div>
              </div>
            </section>
          </main>
        </div>
      </div>
    </div>
  );
}
