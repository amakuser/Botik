import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AppShell } from "../../shared/ui/AppShell";
import { listJobs, startJob, stopJob } from "../../shared/api/client";
import { JobState, JobSummary } from "../../shared/contracts";
import { ModelScopeStatusCard } from "./components/ModelScopeStatusCard";
import { ModelsRegistryTable } from "./components/ModelsRegistryTable";
import { ModelsSummaryCard } from "./components/ModelsSummaryCard";
import { TrainingControlCard } from "./components/TrainingControlCard";
import { TrainingRunsTable } from "./components/TrainingRunsTable";
import { useModelsReadModel } from "./hooks/useModelsReadModel";

const ACTIVE_STATES: JobState[] = ["queued", "starting", "running", "stopping"];

function truncatedLabel(value: boolean) {
  return value ? "Showing bounded recent rows." : "Showing all rows in the current bounded snapshot.";
}

export function ModelsPage() {
  const queryClient = useQueryClient();
  const modelsQuery = useModelsReadModel();
  const snapshot = modelsQuery.data;
  const [actionError, setActionError] = useState<string | null>(null);
  const jobsQuery = useQuery({
    queryKey: ["jobs"],
    queryFn: listJobs,
    refetchInterval: 2_000,
  });
  const jobs = jobsQuery.data ?? [];
  const activeJob = jobs.find((job) => ACTIVE_STATES.includes(job.state));
  const activeTrainingJob = jobs.find(
    (job) => job.job_type === "training_control" && ACTIVE_STATES.includes(job.state),
  );
  const latestTrainingJob = jobs.find((job) => job.job_type === "training_control") ?? null;

  async function handleStartTraining() {
    setActionError(null);
    try {
      await startJob({
        job_type: "training_control",
        payload: {
          scope: "futures",
          interval: "1m",
        },
      });
      await queryClient.invalidateQueries({ queryKey: ["jobs"] });
      await queryClient.invalidateQueries({ queryKey: ["models-read-model"] });
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Failed to start futures training.");
    }
  }

  async function handleStopTraining() {
    if (!activeTrainingJob) {
      return;
    }
    setActionError(null);
    try {
      await stopJob(activeTrainingJob.job_id, { reason: "models-training-stop" });
      await queryClient.invalidateQueries({ queryKey: ["jobs"] });
      await queryClient.invalidateQueries({ queryKey: ["models-read-model"] });
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Failed to stop futures training.");
    }
  }

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

        {actionError ? (
          <section className="panel">
            <h2>Training Control Error</h2>
            <p className="inline-error" data-testid="models.training-control.error">
              {actionError}
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

        <TrainingControlCard
          job={(activeTrainingJob ?? latestTrainingJob) as JobSummary | null}
          startDisabled={Boolean(activeJob)}
          stopDisabled={!activeTrainingJob}
          onStart={() => void handleStartTraining()}
          onStop={() => void handleStopTraining()}
        />

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
