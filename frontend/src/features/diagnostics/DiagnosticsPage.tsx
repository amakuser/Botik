import { AppShell } from "../../shared/ui/AppShell";
import { useDiagnosticsModel } from "./hooks/useDiagnosticsModel";

function boolLabel(value: boolean) {
  return value ? "yes" : "no";
}

export function DiagnosticsPage() {
  const diagnosticsQuery = useDiagnosticsModel();
  const snapshot = diagnosticsQuery.data;

  return (
    <AppShell>
      <div className="diagnostics-layout">
        <section className="panel">
          <h2>Settings / Diagnostics Compatibility</h2>
          <p className="panel-muted">
            Read-only resolved config, path, and compatibility diagnostics for the already migrated new-stack product
            path.
          </p>
          <p className="status-caption" data-testid="diagnostics.source-mode">
            Source mode: {snapshot?.source_mode ?? "loading"}
          </p>
        </section>

        {diagnosticsQuery.isError ? (
          <section className="panel">
            <h2>Diagnostics Error</h2>
            <p className="inline-error" data-testid="diagnostics.error">
              Failed to load the diagnostics snapshot.
            </p>
          </section>
        ) : null}

        <section className="analytics-summary-grid">
          <section className="panel" data-testid="diagnostics.summary.routes">
            <p className="spot-summary-card__label">Routes</p>
            <p className="spot-summary-card__value">{snapshot?.summary.routes_count ?? "..."}</p>
            <p className="summary-card__note">Migrated route count currently visible on the new stack.</p>
          </section>
          <section className="panel" data-testid="diagnostics.summary.fixtures">
            <p className="spot-summary-card__label">Fixture Overrides</p>
            <p className="spot-summary-card__value">{snapshot?.summary.fixture_overrides_count ?? "..."}</p>
            <p className="summary-card__note">Current fixture-backed compatibility inputs in the resolved settings.</p>
          </section>
          <section className="panel" data-testid="diagnostics.summary.missing-paths">
            <p className="spot-summary-card__label">Missing Paths</p>
            <p className="spot-summary-card__value">{snapshot?.summary.missing_paths_count ?? "..."}</p>
            <p className="summary-card__note">Missing paths across the bounded diagnostics snapshot.</p>
          </section>
          <section className="panel" data-testid="diagnostics.summary.runtime-mode">
            <p className="spot-summary-card__label">Runtime Control Mode</p>
            <p className="spot-summary-card__value">{snapshot?.summary.runtime_control_mode ?? "..."}</p>
            <p className="summary-card__note">Current runtime-control mode for the migrated runtime surface.</p>
          </section>
        </section>

        <section className="panel">
          <div className="surface-panel__header">
            <div>
              <h2>Resolved Config</h2>
              <p className="panel-muted">Masked where appropriate. No settings editing is exposed in this slice.</p>
            </div>
          </div>
          <div className="surface-table-wrap">
            <table className="surface-table">
              <thead>
                <tr>
                  <th>Label</th>
                  <th>Value</th>
                  <th>Masked</th>
                </tr>
              </thead>
              <tbody>
                {(snapshot?.config ?? []).map((entry, index) => (
                  <tr key={entry.key} data-testid={`diagnostics.config.${index}`}>
                    <td>{entry.label}</td>
                    <td>{entry.value}</td>
                    <td>{boolLabel(entry.masked)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="panel">
          <div className="surface-panel__header">
            <div>
              <h2>Resolved Paths</h2>
              <p className="panel-muted">Read-only path/config diagnostics for the current migrated flows.</p>
            </div>
          </div>
          <div className="surface-table-wrap">
            <table className="surface-table">
              <thead>
                <tr>
                  <th>Label</th>
                  <th>Source</th>
                  <th>Kind</th>
                  <th>Exists</th>
                  <th>Path</th>
                </tr>
              </thead>
              <tbody>
                {(snapshot?.paths ?? []).map((entry) => (
                  <tr key={entry.key} data-testid={`diagnostics.path.${entry.key}`}>
                    <td>{entry.label}</td>
                    <td>{entry.source}</td>
                    <td>{entry.kind}</td>
                    <td>{boolLabel(entry.exists)}</td>
                    <td>{entry.path}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="panel">
          <div className="surface-panel__header">
            <div>
              <h2>Warnings</h2>
              <p className="panel-muted">Bounded compatibility warnings only, with no mutation controls.</p>
            </div>
          </div>
          {(snapshot?.warnings ?? []).length > 0 ? (
            <ul className="diagnostics-warning-list">
              {(snapshot?.warnings ?? []).map((warning, index) => (
                <li key={`${warning}-${index}`} data-testid={`diagnostics.warning.${index}`}>
                  {warning}
                </li>
              ))}
            </ul>
          ) : (
            <p className="panel-muted" data-testid="diagnostics.warnings.empty">
              No compatibility warnings in the current bounded snapshot.
            </p>
          )}
        </section>
      </div>
    </AppShell>
  );
}
