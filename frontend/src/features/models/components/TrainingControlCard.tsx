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

export function TrainingControlCard({
  job,
  startDisabled,
  stopDisabled,
  onStart,
  onStop,
}: TrainingControlCardProps) {
  return (
    <section className="panel" data-testid="models.training-control">
      <div className="surface-panel__header">
        <div>
          <h2>Training Control</h2>
          <p className="panel-muted">
            One bounded futures training path through the existing Job Manager flow. Live logs stay visible in Job
            Monitor and the `jobs` log channel.
          </p>
        </div>
      </div>

      <dl className="job-preset-grid">
        <dt>Scope</dt>
        <dd data-testid="models.training-control.scope">futures</dd>
        <dt>Interval</dt>
        <dd data-testid="models.training-control.interval">1m</dd>
        <dt>Current Job</dt>
        <dd data-testid="models.training-control.state">{formatState(job)}</dd>
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
