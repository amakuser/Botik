import { JobDetails, JobState } from "../../../shared/contracts";
import { SectionHeading } from "../../../shared/ui/SectionHeading";

interface JobStatusCardProps {
  job: JobDetails | null;
}

function toPercentage(progress: number | undefined) {
  return `${Math.round((progress ?? 0) * 100)}%`;
}

function formatDateTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString() : "n/a";
}

function statusClassName(state: JobState | undefined) {
  if (!state) {
    return "status-chip";
  }
  return `status-chip is-${state}`;
}

export function JobStatusCard({ job }: JobStatusCardProps) {
  if (!job) {
    return (
      <section
        className="panel jobs-selected-panel"
        data-ui-role="job-status"
        data-ui-scope="selected"
        data-ui-state="empty"
      >
        <SectionHeading title="Выбранная задача" description="Контекст выполнения и прогресс." />
        <p
          className="panel-muted"
          data-testid="jobs.selected.empty"
          data-ui-role="empty-state"
          data-ui-scope="job-status"
        >
          Задача ещё не запускалась.
        </p>
      </section>
    );
  }

  const progress = Math.round((job.progress ?? 0) * 100);

  return (
    <section
      className="panel jobs-selected-panel"
      data-ui-role="job-status"
      data-ui-scope="selected"
      data-ui-state={job.state}
    >
      <SectionHeading title="Выбранная задача" description="Контекст выполнения и прогресс." />

      <div className="jobs-selected__topline">
        <div className="jobs-selected__identity">
          <p className="jobs-selected__eyebrow">Текущая задача</p>
          <h3 data-testid="jobs.selected.job-type">{job.job_type}</h3>
        </div>
        <span
          className={statusClassName(job.state)}
          data-testid="jobs.selected.state"
          data-ui-role="status-badge"
          data-ui-scope="selected-job"
          data-ui-state={job.state}
        >
          {job.state}
        </span>
      </div>

      <div className="jobs-progress-card">
        <div className="jobs-progress-card__header">
          <span className="jobs-progress-card__label">Прогресс</span>
          <strong data-testid="jobs.selected.progress">{toPercentage(job.progress)}</strong>
        </div>
        <div className="jobs-progress-card__track" aria-hidden="true">
          <span className="jobs-progress-card__bar" style={{ width: `${progress}%` }} />
        </div>
      </div>

      <dl className="status-grid">
        <dt>Job ID</dt>
        <dd data-testid="jobs.selected.id">{job.job_id}</dd>
        <dt>Обновлено</dt>
        <dd>{formatDateTime(job.updated_at)}</dd>
        <dt>Запущено</dt>
        <dd>{formatDateTime(job.started_at)}</dd>
        <dt>Код выхода</dt>
        <dd>{job.exit_code ?? "n/a"}</dd>
      </dl>
      {job.last_error ? (
        <div
          className="jobs-selected__callout jobs-selected__callout--error"
          data-ui-role="status-callout"
          data-ui-scope="selected-job"
          data-ui-kind="error"
        >
          <span className="jobs-selected__callout-label">Последняя ошибка</span>
          <p className="inline-error" data-testid="jobs.selected.error">
            {job.last_error}
          </p>
        </div>
      ) : (
        <div
          className="jobs-selected__callout"
          data-ui-role="status-callout"
          data-ui-scope="selected-job"
          data-ui-kind="info"
        >
          <span className="jobs-selected__callout-label">Статус</span>
          <p className="status-caption" data-testid="jobs.selected.caption">
            Прогресс и логи передаются через SSE.
          </p>
        </div>
      )}
    </section>
  );
}
