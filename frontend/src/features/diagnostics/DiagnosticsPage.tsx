import { AppShell } from "../../shared/ui/AppShell";
import { PageIntro } from "../../shared/ui/PageIntro";
import { SectionHeading } from "../../shared/ui/SectionHeading";
import { useDiagnosticsModel } from "./hooks/useDiagnosticsModel";

function boolLabel(value: boolean) {
  return value ? "yes" : "no";
}

export function DiagnosticsPage() {
  const diagnosticsQuery = useDiagnosticsModel();
  const snapshot = diagnosticsQuery.data;
  const configEntries = snapshot?.config ?? [];
  const pathEntries = snapshot?.paths ?? [];
  const warnings = snapshot?.warnings ?? [];

  return (
    <AppShell>
      <div className="app-route diagnostics-layout">
        <PageIntro
          eyebrow="Diagnostics"
          title="Settings / Diagnostics Compatibility"
          description="Read-only resolved config, path, and compatibility diagnostics for the already migrated primary product path."
          meta={
            <>
              <p className="status-caption" data-testid="diagnostics.source-mode">
                Source mode: {snapshot?.source_mode ?? "loading"}
              </p>
              <p className="status-caption">Warnings: {snapshot?.summary.warnings_count ?? "loading"}</p>
              <p className="status-caption">Missing paths: {snapshot?.summary.missing_paths_count ?? "loading"}</p>
              <p className="status-caption">Runtime mode: {snapshot?.summary.runtime_control_mode ?? "loading"}</p>
            </>
          }
        />

        {diagnosticsQuery.isError ? (
          <section className="panel diagnostics-warning-panel">
            <SectionHeading
              title="Diagnostics Error"
              description="The route remains read-only; this only affects diagnostics visibility."
            />
            <p className="inline-error" data-testid="diagnostics.error">
              Failed to load the diagnostics snapshot.
            </p>
          </section>
        ) : null}

        <section className="panel diagnostics-summary-panel">
          <SectionHeading
            title="Compatibility Snapshot"
            description="Current resolved environment, fixture usage, and path-health posture for the migrated product path."
          />
          <div className="diagnostics-summary-grid">
            <section className="summary-card diagnostics-summary-card" data-testid="diagnostics.summary.routes">
              <p className="diagnostics-summary-card__eyebrow">Coverage</p>
              <p className="diagnostics-summary-card__label">Routes</p>
              <p className="diagnostics-summary-card__value">{snapshot?.summary.routes_count ?? "..."}</p>
              <p className="summary-card__note">Migrated route count currently visible on the new stack.</p>
            </section>
            <section className="summary-card diagnostics-summary-card" data-testid="diagnostics.summary.fixtures">
              <p className="diagnostics-summary-card__eyebrow">Inputs</p>
              <p className="diagnostics-summary-card__label">Fixture Overrides</p>
              <p className="diagnostics-summary-card__value">{snapshot?.summary.fixture_overrides_count ?? "..."}</p>
              <p className="summary-card__note">Current fixture-backed compatibility inputs in the resolved settings.</p>
            </section>
            <section className="summary-card diagnostics-summary-card" data-testid="diagnostics.summary.missing-paths">
              <p className="diagnostics-summary-card__eyebrow">Path Health</p>
              <p className="diagnostics-summary-card__label">Missing Paths</p>
              <p className="diagnostics-summary-card__value">{snapshot?.summary.missing_paths_count ?? "..."}</p>
              <p className="summary-card__note">Missing paths across the bounded diagnostics snapshot.</p>
            </section>
            <section className="summary-card diagnostics-summary-card" data-testid="diagnostics.summary.runtime-mode">
              <p className="diagnostics-summary-card__eyebrow">Control</p>
              <p className="diagnostics-summary-card__label">Runtime Control Mode</p>
              <p className="diagnostics-summary-card__value">{snapshot?.summary.runtime_control_mode ?? "..."}</p>
              <p className="summary-card__note">Current runtime-control mode for the migrated runtime surface.</p>
            </section>
          </div>
        </section>

        <section className="panel diagnostics-panel">
          <SectionHeading title="Resolved Config" description="Masked where appropriate. No settings editing is exposed in this slice." />
          {configEntries.length > 0 ? (
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
                  {configEntries.map((entry, index) => (
                    <tr key={entry.key} data-testid={`diagnostics.config.${index}`}>
                      <td className="surface-table__primary">{entry.label}</td>
                      <td>
                        <span className="diagnostics-code">{entry.value}</span>
                      </td>
                      <td>
                        <span className={entry.masked ? "surface-badge surface-badge--soft" : "surface-badge"}>
                          {boolLabel(entry.masked)}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="surface-table-empty" data-testid="diagnostics.config.empty">
              <strong>No resolved config entries</strong>
              <p>The current bounded snapshot did not expose any config values.</p>
            </div>
          )}
        </section>

        <section className="panel diagnostics-panel">
          <SectionHeading title="Resolved Paths" description="Read-only path/config diagnostics for the current migrated flows." />
          {pathEntries.length > 0 ? (
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
                  {pathEntries.map((entry) => (
                    <tr key={entry.key} data-testid={`diagnostics.path.${entry.key}`}>
                      <td className="surface-table__primary">{entry.label}</td>
                      <td>
                        <span className="surface-badge surface-badge--soft">{entry.source}</span>
                      </td>
                      <td>{entry.kind}</td>
                      <td>
                        <span className={entry.exists ? "surface-badge surface-badge--buy" : "surface-badge surface-badge--sell"}>
                          {boolLabel(entry.exists)}
                        </span>
                      </td>
                      <td>
                        <span className="diagnostics-code diagnostics-code--path">{entry.path}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="surface-table-empty" data-testid="diagnostics.paths.empty">
              <strong>No resolved paths</strong>
              <p>The current bounded diagnostics snapshot did not return any path rows.</p>
            </div>
          )}
        </section>

        <section className="panel diagnostics-warning-panel">
          <SectionHeading title="Warnings" description="Bounded compatibility warnings only, with no mutation controls." />
          {warnings.length > 0 ? (
            <ul className="diagnostics-warning-list">
              {warnings.map((warning, index) => (
                <li key={`${warning}-${index}`} data-testid={`diagnostics.warning.${index}`} className="diagnostics-warning-item">
                  <span className="diagnostics-warning-item__badge">Attention</span>
                  <span>{warning}</span>
                </li>
              ))}
            </ul>
          ) : (
            <div className="surface-table-empty" data-testid="diagnostics.warnings.empty">
              <strong>No compatibility warnings</strong>
              <p>No bounded warnings were present in the current diagnostics snapshot.</p>
            </div>
          )}
        </section>
      </div>
    </AppShell>
  );
}
