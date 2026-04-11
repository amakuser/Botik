import { AppShell } from "../../shared/ui/AppShell";
import { ModelScopeStatusCard } from "./components/ModelScopeStatusCard";
import { ModelsRegistryTable } from "./components/ModelsRegistryTable";
import { ModelsSummaryCard } from "./components/ModelsSummaryCard";
import { TrainingRunsTable } from "./components/TrainingRunsTable";
import { useModelsReadModel } from "./hooks/useModelsReadModel";

function truncatedLabel(value: boolean) {
  return value ? "Showing bounded recent rows." : "Showing all rows in the current bounded snapshot.";
}

export function ModelsPage() {
  const modelsQuery = useModelsReadModel();
  const snapshot = modelsQuery.data;

  return (
    <AppShell>
      <div className="models-layout">
        <section className="panel">
          <h2>Models Registry / Training Status</h2>
          <p className="panel-muted">
            Read-only model registry summary, latest declared model info, and bounded recent training-run visibility on
            the new stack.
          </p>
          <p className="status-caption" data-testid="models.source-mode">
            Source mode: {snapshot?.source_mode ?? "loading"}
          </p>
        </section>

        {modelsQuery.isError ? (
          <section className="panel">
            <h2>Models Read Error</h2>
            <p className="inline-error" data-testid="models.error">
              Failed to load the models read model.
            </p>
          </section>
        ) : null}

        <section className="models-summary-grid">
          <ModelsSummaryCard
            label="Total Models"
            value={snapshot?.summary.total_models ?? "..."}
            note="Bounded registry inventory only."
            testId="models.summary.total-models"
          />
          <ModelsSummaryCard
            label="Active Declared"
            value={snapshot?.summary.active_declared_count ?? "..."}
            note={`Manifest: ${snapshot?.summary.manifest_status ?? "loading"}`}
            testId="models.summary.active-declared"
          />
          <ModelsSummaryCard
            label="Ready Scopes"
            value={snapshot?.summary.ready_scopes ?? "..."}
            note="Spot + futures read-only readiness snapshot."
            testId="models.summary.ready-scopes"
          />
          <ModelsSummaryCard
            label="Recent Runs"
            value={snapshot?.summary.recent_training_runs_count ?? "..."}
            note={`Latest: ${snapshot?.summary.latest_run_scope ?? "loading"} / ${snapshot?.summary.latest_run_status ?? "loading"}`}
            testId="models.summary.recent-runs"
          />
        </section>

        <section className="models-scope-grid">
          {(snapshot?.scopes ?? []).map((scopeStatus) => (
            <ModelScopeStatusCard key={scopeStatus.scope} scopeStatus={scopeStatus} />
          ))}
        </section>

        <section className="panel">
          <div className="surface-panel__header">
            <div>
              <h2>Registry Entries</h2>
              <p className="panel-muted">{truncatedLabel(snapshot?.truncated.registry_entries ?? false)}</p>
            </div>
          </div>
          <ModelsRegistryTable entries={snapshot?.registry_entries ?? []} />
        </section>

        <section className="panel">
          <div className="surface-panel__header">
            <div>
              <h2>Recent Training Runs</h2>
              <p className="panel-muted">{truncatedLabel(snapshot?.truncated.recent_training_runs ?? false)}</p>
            </div>
          </div>
          <TrainingRunsTable runs={snapshot?.recent_training_runs ?? []} />
        </section>
      </div>
    </AppShell>
  );
}
