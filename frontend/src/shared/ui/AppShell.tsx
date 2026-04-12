import { NavLink } from "react-router-dom";
import { PropsWithChildren } from "react";
import { DesktopFrame } from "./DesktopFrame";

type NavItem = {
  to: string;
  label: string;
  end?: boolean;
};

type NavGroup = {
  label: string;
  items: NavItem[];
};

const NAV_GROUPS: NavGroup[] = [
  {
    label: "Core",
    items: [
      { to: "/", label: "Foundation Health", end: true },
      { to: "/jobs", label: "Job Monitor" },
      { to: "/logs", label: "Unified Logs" },
      { to: "/runtime", label: "Runtime Control" },
    ],
  },
  {
    label: "Surfaces",
    items: [
      { to: "/spot", label: "Spot Read" },
      { to: "/futures", label: "Futures Read" },
      { to: "/telegram", label: "Telegram Ops" },
      { to: "/analytics", label: "PnL / Analytics" },
      { to: "/models", label: "Models / Status" },
      { to: "/diagnostics", label: "Diagnostics" },
    ],
  },
];

export function AppShell({ children }: PropsWithChildren) {
  return (
    <DesktopFrame>
      <div className="app-shell" data-testid="foundation.app-shell">
        <aside className="app-shell__sidebar">
          <header className="app-shell__header">
            <p className="app-shell__eyebrow">Primary Product Path</p>
            <h1>Botik Foundation</h1>
            <p className="app-shell__subtitle">
              Tauri desktop shell, app-service, and migrated operator surfaces on the current primary stack.
            </p>
          </header>

          <nav className="app-shell__nav" aria-label="Primary">
            {NAV_GROUPS.map((group) => (
              <section key={group.label} className="app-shell__nav-group" aria-labelledby={`nav-group-${group.label}`}>
                <p id={`nav-group-${group.label}`} className="app-shell__nav-group-title">
                  {group.label}
                </p>
                <div className="app-shell__nav-links">
                  {group.items.map((item) => (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      end={item.end}
                      className={({ isActive }) => (isActive ? "app-shell__nav-link is-active" : "app-shell__nav-link")}
                    >
                      {item.label}
                    </NavLink>
                  ))}
                </div>
              </section>
            ))}
          </nav>
        </aside>

        <main className="app-shell__main">
          <div className="app-shell__content">{children}</div>
        </main>
      </div>
    </DesktopFrame>
  );
}
