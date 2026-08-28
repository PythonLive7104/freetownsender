import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { Icon } from "../icons";
import { useTheme } from "../theme";
import { useAuth } from "../auth";
import WorkspaceSwitcher from "./WorkspaceSwitcher";
import OnboardingGuide from "./OnboardingGuide";
import { prefetchPage } from "../pageLoaders";
import HelpDock from "./HelpDock";

const NAV = [
  { section: "Main", items: [["/", "Dashboard", "dashboard", true]] },
  {
    section: "Automation",
    items: [
      ["/mailboxes", "Mailbox", "mailbox"],
      ["/auto-reply", "Auto-reply", "reply"],
      ["/rules", "Rules", "rules"],
      ["/configuration", "Configuration", "config"],
      ["/listeners", "Listeners", "listeners"],
      ["/check", "Check", "watch"],
    ],
  },
  {
    section: "Tools",
    items: [
      ["/placeholders", "Placeholders", "placeholders"],
      ["/links", "Links", "links"],
      ["/attachments", "Attachments", "attachments"],
      ["/proxies", "Proxies", "proxy"],
    ],
  },
  {
    section: "System",
    items: [
      ["/team", "Team", "team"],
      ["/billing", "Subscription", "bolt"],
      ["/security", "Security", "security"],
      ["/telegram", "Telegram", "telegram"],
      ["/settings", "Settings", "settings"],
    ],
  },
];

const TITLES = {
  "/": ["Dashboard", "Live system overview"],
  "/mailboxes": ["Mailboxes", "Connect and manage email accounts"],
  "/auto-reply": ["Auto-reply", "Saved reply templates"],
  "/rules": ["Rules", "Subject-based matching rules"],
  "/configuration": ["Configuration", "Automation engine settings"],
  "/listeners": ["Listeners", "Mailbox polling status & live mail feed"],
  "/check": ["Check", "Keyword watches across your mailboxes"],
  "/placeholders": ["Placeholders", "Reusable template variables"],
  "/team": ["Team", "Workspace members & sharing"],
  "/billing": ["Subscription", "Your plan & payments"],
  "/links": ["Links", "Reusable tracked links with click counts"],
  "/attachments": ["Attachments", "Reusable files to attach to auto-replies"],
  "/proxies": ["Proxies", "Rotate outgoing IPs for SMTP sending"],
  "/security": ["Security", "Access & credentials"],
  "/telegram": ["Telegram", "Telegram notifications"],
  "/settings": ["Settings", "Your account & app preferences"],
};

export default function Layout() {
  const { theme, toggle } = useTheme();
  const { user, logout, completeOnboarding } = useAuth();
  const nav = useNavigate();
  const { pathname } = useLocation();
  const [title, sub] = TITLES[pathname] || ["EndTime Auto-Reply", ""];
  const [navOpen, setNavOpen] = useState(false);
  const [guideOpen, setGuideOpen] = useState(false);

  // Close the mobile drawer whenever the route changes.
  useEffect(() => { setNavOpen(false); }, [pathname]);

  // Auto-open the setup guide on first login (until it's completed or skipped).
  useEffect(() => {
    if (user && !user.onboarding_completed) setGuideOpen(true);
  }, [user?.id, user?.onboarding_completed]);

  // Closing the guide (Finish or Skip) marks it seen so it won't reopen next login.
  const closeGuide = () => {
    setGuideOpen(false);
    if (user && !user.onboarding_completed) completeOnboarding();
  };

  const handleLogout = async () => { await logout(); nav("/login"); };

  return (
    <div className="app">
      <div className={`nav-backdrop ${navOpen ? "show" : ""}`} onClick={() => setNavOpen(false)} />
      <aside className={`sidebar ${navOpen ? "open" : ""}`}>
        <div className="brand">
          <div className="brand-logo"><Icon.hourglass /></div>
          <div>
            <div className="brand-name">EndTime <span className="nowrap">Auto-Reply</span></div>
            <div className="brand-sub">Admin Panel</div>
          </div>
          <button className="btn icon-btn nav-close" onClick={() => setNavOpen(false)} title="Close menu">
            <Icon.close />
          </button>
        </div>

        {/* Only the nav scrolls; the footer below stays pinned so Logout is always
            reachable, even where the menu is taller than the window. */}
        <div className="nav-scroll">
        {NAV.map((group) => (
          <div className="nav-group" key={group.section}>
            <div className="nav-label">{group.section}</div>
            {group.items.map(([to, label, icon, end]) => {
              const IconCmp = Icon[icon];
              return (
                <NavLink
                  key={to}
                  to={to}
                  end={end}
                  // Start fetching the page's chunk on hover/focus, so by the time the
                  // click registers it is usually already there.
                  onMouseEnter={() => prefetchPage(to)}
                  onFocus={() => prefetchPage(to)}
                  className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
                >
                  <IconCmp />
                  <span>{label}</span>
                </NavLink>
              );
            })}
          </div>
        ))}
        </div>

        <div className="sidebar-footer">
          <div className="nav-item" style={{ pointerEvents: "none" }}>
            <span className="status-dot" />
            <span style={{ fontSize: 12.5 }}>Listening · 30s</span>
          </div>
          {user && (
            <div className="nav-item" style={{ pointerEvents: "none", gap: 10 }}>
              <div className="brand-logo" style={{ width: 26, height: 26, fontSize: 12, borderRadius: 8 }}>
                {user.username?.[0]?.toUpperCase()}
              </div>
              <span style={{ fontSize: 12.5, overflow: "hidden", textOverflow: "ellipsis" }}>{user.username}</span>
            </div>
          )}
          <div className="nav-item" onClick={handleLogout}><Icon.logout /><span>Logout</span></div>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <div className="topbar-lead">
            <button className="btn icon-btn nav-toggle" onClick={() => setNavOpen(true)} title="Menu">
              <Icon.menu />
            </button>
            <div className="topbar-titles">
              <h1 className="page-title">{title}</h1>
              {sub && <div className="page-sub">{sub}</div>}
            </div>
          </div>
          <div className="topbar-actions">
            <WorkspaceSwitcher current={user?.workspace} />
            <button className="btn icon-btn" onClick={toggle} title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}>
              {theme === "dark" ? <Icon.sun /> : <Icon.moon />}
            </button>
            <span className="badge badge-live"><span className="pulse" />Active · 30s poll</span>
          </div>
        </header>
        <main className="content">
          <Outlet context={{ openGuide: () => setGuideOpen(true) }} />
        </main>
      </div>

      <HelpDock onOpenGuide={() => setGuideOpen(true)} />
      <OnboardingGuide open={guideOpen} onClose={closeGuide} />
    </div>
  );
}
