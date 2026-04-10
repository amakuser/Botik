import { NavLink } from "react-router-dom";
import { PropsWithChildren } from "react";

export function AppShell({ children }: PropsWithChildren) {
  return (
    <div className="app-shell" data-testid="foundation.app-shell">
      <header className="app-shell__header">
        <h1>Botik Foundation</h1>
        <p>Phase A foundation scaffold</p>
        <nav className="app-shell__nav" aria-label="Primary">
          <NavLink to="/" end className={({ isActive }) => (isActive ? "app-shell__nav-link is-active" : "app-shell__nav-link")}>
            Foundation Health
          </NavLink>
          <NavLink to="/jobs" className={({ isActive }) => (isActive ? "app-shell__nav-link is-active" : "app-shell__nav-link")}>
            Job Monitor
          </NavLink>
          <NavLink to="/logs" className={({ isActive }) => (isActive ? "app-shell__nav-link is-active" : "app-shell__nav-link")}>
            Unified Logs
          </NavLink>
        </nav>
      </header>
      <main className="app-shell__content">{children}</main>
    </div>
  );
}
