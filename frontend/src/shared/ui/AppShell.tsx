import { PropsWithChildren } from "react";

export function AppShell({ children }: PropsWithChildren) {
  return (
    <div className="app-shell" data-testid="foundation.app-shell">
      <header className="app-shell__header">
        <h1>Botik Foundation</h1>
        <p>Phase A foundation scaffold</p>
      </header>
      <main className="app-shell__content">{children}</main>
    </div>
  );
}
