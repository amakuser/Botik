import type { RuntimeStatus } from "../../../shared/contracts";

function formatAge(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "n/a";
  }
  if (value < 60) {
    return `${Math.round(value)}s ago`;
  }
  return `${Math.round(value / 60)}m ago`;
}

interface RuntimeStatusCardProps {
  runtime: RuntimeStatus;
  startDisabled: boolean;
  stopDisabled: boolean;
  onStart: () => void;
  onStop: () => void;
}

export function RuntimeStatusCard({ runtime, startDisabled, stopDisabled, onStart, onStop }: RuntimeStatusCardProps) {
  return (
    <article className="runtime-card panel" data-testid={`runtime.card.${runtime.runtime_id}`}>
      <div className="runtime-card__header">
        <div>
          <h2>{runtime.label}</h2>
          <p className="panel-muted">Bounded start/stop with observable heartbeat and last-error status.</p>
        </div>
        <span className={`runtime-state runtime-state--${runtime.state}`} data-testid={`runtime.state.${runtime.runtime_id}`}>
          {runtime.state.toUpperCase()}
        </span>
      </div>

      <dl className="runtime-card__details">
        <div>
          <dt>PIDs</dt>
          <dd data-testid={`runtime.pids.${runtime.runtime_id}`}>{runtime.pid_count > 0 ? runtime.pids.join(", ") : "none"}</dd>
        </div>
        <div>
          <dt>Heartbeat</dt>
          <dd data-testid={`runtime.heartbeat.${runtime.runtime_id}`}>{formatAge(runtime.last_heartbeat_age_seconds)}</dd>
        </div>
        <div>
          <dt>Last Error</dt>
          <dd data-testid={`runtime.error.${runtime.runtime_id}`}>{runtime.last_error ?? "none"}</dd>
        </div>
        <div>
          <dt>Source</dt>
          <dd data-testid={`runtime.source.${runtime.runtime_id}`}>{runtime.source_mode}</dd>
        </div>
      </dl>

      <p className="runtime-card__reason" data-testid={`runtime.reason.${runtime.runtime_id}`}>
        {runtime.status_reason}
      </p>

      <div className="runtime-card__actions">
        <button
          type="button"
          className="button-primary"
          data-testid={`runtime.start.${runtime.runtime_id}`}
          disabled={startDisabled}
          onClick={onStart}
        >
          Start
        </button>
        <button
          type="button"
          className="button-secondary"
          data-testid={`runtime.stop.${runtime.runtime_id}`}
          disabled={stopDisabled}
          onClick={onStop}
        >
          Stop
        </button>
      </div>
    </article>
  );
}
