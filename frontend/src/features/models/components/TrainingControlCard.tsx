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
          <p className="models-training-card__eyebrow">Control Surface</p>
          <h2>Training Control</h2>
          <p className="panel-muted">
            One bounded futures training path through the existing Job Manager flow. Live logs stay visible in Job
            Monitor and the `jobs` log channel.
          </p>
        </div>
        <span className={stateClass(job)}>{formatState(job)}</span>
      </div>

      <div className="models-training-card__signals">
        <div className="runtime-card__signal">
          <span className="runtime-card__signal-label">Scope</span>
          <strong data-testid="models.training-control.scope">futures</strong>
          <span className="panel-muted">The only bounded training-control path in this phase.</span>
        </div>
        <div className="runtime-card__signal">
          <span className="runtime-card__signal-label">Interval</span>
          <strong data-testid="models.training-control.interval">1m</strong>
          <span className="panel-muted">Fixed interval for deterministic control and verification.</span>
        </div>
        <div className="runtime-card__signal">
          <span className="runtime-card__signal-label">Current job</span>
          <strong data-testid="models.training-control.state">{formatState(job)}</strong>
          <span className="panel-muted">Updated by the existing Job Manager flow.</span>
        </div>
      </div>

      <dl className="job-preset-grid models-training-card__details">
        <dt>Job ID</dt>
        <dd>{job?.job_id ?? "not running"}</dd>
        <dt>Last Updated</dt>
        <dd>{job?.updated_at ?? "not available"}</dd>
      </dl>

      <div className="toolbar-actions">
        <button type="button" className="button-primary" onClick={onStart} disabled={startDisabled}>
          Start Futures Training
        </button>
        <button type="button" className="button-secondary" onClick={onStop} disabled={stopDisabled}>
          Stop Futures Training
        </button>
      </div>
    </section>
  );
}
