import { JobDetails, JobState } from "../../../shared/contracts";

interface JobStatusCardProps {
  job: JobDetails | null;
}

function toPercentage(progress: number | undefined) {
  return `${Math.round((progress ?? 0) * 100)}%`;
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
      <section className="panel" aria-labelledby="job-status-title">
        <h2 id="job-status-title">Selected Job</h2>
        <p className="panel-muted" data-testid="jobs.selected.empty">
          No sample job has been started yet.
        </p>
      </section>
    );
  }

  return (
    <section className="panel" aria-labelledby="job-status-title">
      <h2 id="job-status-title">Selected Job</h2>
      <dl className="status-grid">
        <dt>Type</dt>
        <dd data-testid="jobs.selected.job-type">{job.job_type}</dd>
        <dt>Status</dt>
        <dd>
          <span className={statusClassName(job.state)} data-testid="jobs.selected.state">
            {job.state}
          </span>
        </dd>
        <dt>Progress</dt>
        <dd data-testid="jobs.selected.progress">{toPercentage(job.progress)}</dd>
        <dt>Job ID</dt>
        <dd data-testid="jobs.selected.id">{job.job_id}</dd>
      </dl>
      {job.last_error ? (
        <p className="inline-error" data-testid="jobs.selected.error">
          {job.last_error}
        </p>
      ) : (
        <p className="status-caption" data-testid="jobs.selected.caption">
          Live progress and logs are streamed over SSE.
        </p>
      )}
    </section>
  );
}
