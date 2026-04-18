import { JobSummary } from "../../../shared/contracts";

interface TrainingControlCardProps {
  job: JobSummary | null;
  startDisabled: boolean;
  stopDisabled: boolean;
  onStart: () => void;
  onStop: () => void;
}

function formatState(job: JobSummary | null) {
  if (!job) {
    return "idle";
  }
  return `${job.state} (${Math.round(job.progress * 100)}%)`;
}

function stateClass(job: JobSummary | null) {
  if (!job) {
    return "status-chip";
  }
  if (job.state === "completed") {
    return "status-chip is-completed";
  }
  if (job.state === "failed" || job.state === "cancelled") {
    return "status-chip is-failed";
  }
  return "status-chip";
}

export function TrainingControlCard({
  job,
  startDisabled,
  stopDisabled,
  onStart,
  onStop,
}: TrainingControlCardProps) {
  return (
    <section className="panel models-training-card" data-testid="models.training-control">
      <div className="surface-panel__header models-training-card__header">
        <div className="models-training-card__title-block">
          <p className="models-training-card__eyebrow">Управление</p>
          <h2>Управление обучением</h2>
          <p className="panel-muted">
            Запуск обучения фьючерсных моделей через Job Manager. Логи доступны в Мониторинге задач.
          </p>
        </div>
        <span className={stateClass(job)}>{formatState(job)}</span>
      </div>

      <div className="models-training-card__signals">
        <div className="runtime-card__signal">
          <span className="runtime-card__signal-label">Скоуп</span>
          <strong data-testid="models.training-control.scope">futures</strong>
          <span className="panel-muted">Единственный путь обучения в текущей фазе.</span>
        </div>
        <div className="runtime-card__signal">
          <span className="runtime-card__signal-label">Интервал</span>
          <strong data-testid="models.training-control.interval">1m</strong>
          <span className="panel-muted">Фиксированный интервал для детерминированного контроля.</span>
        </div>
        <div className="runtime-card__signal">
          <span className="runtime-card__signal-label">Текущая задача</span>
          <strong data-testid="models.training-control.state">{formatState(job)}</strong>
          <span className="panel-muted">Обновляется через Job Manager.</span>
        </div>
      </div>

      <dl className="job-preset-grid models-training-card__details">
        <dt>Job ID</dt>
        <dd>{job?.job_id ?? "не запущено"}</dd>
        <dt>Обновлено</dt>
        <dd>{job?.updated_at ?? "нет данных"}</dd>
      </dl>

      <div className="toolbar-actions">
        <button type="button" className="button-primary" onClick={onStart} disabled={startDisabled}>
          Запустить обучение
        </button>
        <button type="button" className="button-secondary" onClick={onStop} disabled={stopDisabled}>
          Остановить обучение
        </button>
      </div>
    </section>
  );
}
