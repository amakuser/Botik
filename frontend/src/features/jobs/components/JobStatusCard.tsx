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
      <section className="panel jobs-selected-panel">
        <SectionHeading title="Selected Job" description="Active execution context and latest bounded progress details." />
        <p className="panel-muted" data-testid="jobs.selected.empty">
          No sample job has been started yet.
        </p>
      </section>
    );
  }

  const progress = Math.round((job.progress ?? 0) * 100);

  return (
    <section className="panel jobs-selected-panel">
      <SectionHeading title="Selected Job" description="Active execution context and latest bounded progress details." />

      <div className="jobs-selected__topline">
        <div className="jobs-selected__identity">
          <p className="jobs-selected__eyebrow">Current Focus</p>
          <h3 data-testid="jobs.selected.job-type">{job.job_type}</h3>
        </div>
        <span className={statusClassName(job.state)} data-testid="jobs.selected.state">
          {job.state}
        </span>
      </div>

      <div className="jobs-progress-card">
        <div className="jobs-progress-card__header">
          <span className="jobs-progress-card__label">Progress</span>
          <strong data-testid="jobs.selected.progress">{toPercentage(job.progress)}</strong>
        </div>
        <div className="jobs-progress-card__track" aria-hidden="true">
          <span className="jobs-progress-card__bar" style={{ width: `${progress}%` }} />
        </div>
      </div>

      <dl className="status-grid">
        <dt>Job ID</dt>
        <dd data-testid="jobs.selected.id">{job.job_id}</dd>
        <dt>Updated</dt>
        <dd>{formatDateTime(job.updated_at)}</dd>
        <dt>Started</dt>
        <dd>{formatDateTime(job.started_at)}</dd>
        <dt>Exit Code</dt>
        <dd>{job.exit_code ?? "n/a"}</dd>
      </dl>
      {job.last_error ? (
        <div className="jobs-selected__callout jobs-selected__callout--error">
          <span className="jobs-selected__callout-label">Last Error</span>
          <p className="inline-error" data-testid="jobs.selected.error">
            {job.last_error}
          </p>
        </div>
      ) : (
        <div className="jobs-selected__callout">
          <span className="jobs-selected__callout-label">Live Status</span>
          <p className="status-caption" data-testid="jobs.selected.caption">
            Live progress and logs are streamed over SSE.
          </p>
        </div>
      )}
    </section>
  );
}
