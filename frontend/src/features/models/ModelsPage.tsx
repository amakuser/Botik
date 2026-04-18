import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AppShell } from "../../shared/ui/AppShell";
import { PageIntro } from "../../shared/ui/PageIntro";
import { SectionHeading } from "../../shared/ui/SectionHeading";
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
  return value ? "Показаны последние записи (обрезано)." : "Показаны все записи текущего снепшота.";
}

export function ModelsPage() {
  const queryClient = useQueryClient();
  const modelsQuery = useModelsReadModel();
  const snapshot = modelsQuery.data;
  const summary = snapshot?.summary;
  const truncated = snapshot?.truncated;
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
      setActionError(error instanceof Error ? error.message : "Не удалось запустить обучение.");
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
      setActionError(error instanceof Error ? error.message : "Не удалось остановить обучение.");
    }
  }

  return (
    <AppShell>
      <div className="app-route models-layout">
        <PageIntro
          eyebrow="Данные"
          title="Реестр моделей / Обучение"
          description="Реестр ML моделей, состояние обучения и последние запуски."
          meta={
            <>
              <p className="status-caption" data-testid="models.source-mode">
                Режим: {snapshot?.source_mode ?? "загрузка"}
              </p>
              <p className="status-caption">Манифест: {summary?.manifest_status ?? "загрузка"}</p>
              <p className="status-caption">Реестр DB: {summary ? (summary.db_available ? "доступен" : "отсутствует") : "загрузка"}</p>
              <p className="status-caption">
                Последний запуск: {summary?.latest_run_scope ?? "загрузка"} / {summary?.latest_run_status ?? "загрузка"}
              </p>
            </>
          }
        />

        {modelsQuery.isError ? (
          <section className="panel">
            <h2>Ошибка загрузки моделей</h2>
            <p className="inline-error" data-testid="models.error">
              Не удалось загрузить данные моделей.
            </p>
          </section>
        ) : null}

        {actionError ? (
          <section className="panel">
            <h2>Ошибка управления обучением</h2>
            <p className="inline-error" data-testid="models.training-control.error">
              {actionError}
            </p>
          </section>
        ) : null}

        <section className="panel models-summary-panel">
          <SectionHeading
            title="Обзор"
            description="Готовность, состояние реестра и свежесть обучения."
          />
          <div className="models-summary-grid">
            <ModelsSummaryCard
              eyebrow="Реестр"
              label="Всего моделей"
              value={summary?.total_models ?? "..."}
              note="Инвентарь реестра."
              testId="models.summary.total-models"
            />
            <ModelsSummaryCard
              eyebrow="Манифест"
              label="Активных объявлений"
              value={summary?.active_declared_count ?? "..."}
              note={`Манифест: ${summary?.manifest_status ?? "загрузка"}`}
              testId="models.summary.active-declared"
            />
            <ModelsSummaryCard
              eyebrow="Готовность"
              label="Готовых скоупов"
              value={summary?.ready_scopes ?? "..."}
              note="Снепшот готовности Spot + Futures."
              testId="models.summary.ready-scopes"
            />
            <ModelsSummaryCard
              eyebrow="Свежесть"
              label="Последних запусков"
              value={summary?.recent_training_runs_count ?? "..."}
              note={`Последний: ${summary?.latest_run_scope ?? "загрузка"} / ${summary?.latest_run_status ?? "загрузка"}`}
              testId="models.summary.recent-runs"
            />
          </div>
        </section>

        <TrainingControlCard
          job={(activeTrainingJob ?? latestTrainingJob) as JobSummary | null}
          startDisabled={Boolean(activeJob)}
          stopDisabled={!activeTrainingJob}
          onStart={() => void handleStartTraining()}
          onStop={() => void handleStopTraining()}
        />

        <section className="panel models-scope-panel">
          <SectionHeading
            title="Состояние моделей"
            description="Готовность объявленных моделей, последний сигнал реестра и обучения по каждому скоупу."
          />
          <div className="models-scope-grid">
            {(snapshot?.scopes ?? []).map((scopeStatus) => (
              <ModelScopeStatusCard key={scopeStatus.scope} scopeStatus={scopeStatus} />
            ))}
          </div>
        </section>

        <section className="panel models-history-panel">
          <SectionHeading title="Записи реестра" description={truncatedLabel(truncated?.registry_entries ?? false)} />
          <ModelsRegistryTable entries={snapshot?.registry_entries ?? []} />
        </section>

        <section className="panel models-history-panel">
          <SectionHeading title="Последние запуски обучения" description={truncatedLabel(truncated?.recent_training_runs ?? false)} />
          <TrainingRunsTable runs={snapshot?.recent_training_runs ?? []} />
        </section>
      </div>
    </AppShell>
  );
}
