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

function formatTimestamp(value: string | null | undefined): string {
  if (!value) {
    return "n/a";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

interface RuntimeStatusCardProps {
  runtime: RuntimeStatus;
  startDisabled: boolean;
  stopDisabled: boolean;
  onStart: () => void;
  onStop: () => void;
}

export function RuntimeStatusCard({ runtime, startDisabled, stopDisabled, onStart, onStop }: RuntimeStatusCardProps) {
  const pids = runtime.pids ?? [];
  const hasError = Boolean(runtime.last_error);

  return (
    <article className="runtime-card panel" data-testid={`runtime.card.${runtime.runtime_id}`}>
      <div className="runtime-card__header">
        <div className="runtime-card__title-block">
          <h2>{runtime.label}</h2>
          <p className="panel-muted">Bounded controls with observable heartbeat, reason, and last-error visibility.</p>
        </div>
        <span className={`runtime-state runtime-state--${runtime.state}`} data-testid={`runtime.state.${runtime.runtime_id}`}>
          {runtime.state.toUpperCase()}
        </span>
      </div>

      <div className="runtime-card__signal-row">
        <div className="runtime-card__signal">
          <span className="runtime-card__signal-label">Heartbeat</span>
          <strong data-testid={`runtime.heartbeat.${runtime.runtime_id}`}>{formatAge(runtime.last_heartbeat_age_seconds)}</strong>
        </div>
        <div className="runtime-card__signal">
          <span className="runtime-card__signal-label">Source</span>
          <strong data-testid={`runtime.source.${runtime.runtime_id}`}>{runtime.source_mode}</strong>
        </div>
      </div>

      <dl className="runtime-card__details">
        <div>
          <dt>PIDs</dt>
          <dd data-testid={`runtime.pids.${runtime.runtime_id}`}>{runtime.pid_count > 0 ? pids.join(", ") : "none"}</dd>
        </div>
        <div>
          <dt>PID Count</dt>
          <dd>{runtime.pid_count}</dd>
        </div>
        <div>
          <dt>Last Heartbeat</dt>
          <dd>{formatTimestamp(runtime.last_heartbeat_at)}</dd>
        </div>
        <div>
          <dt>Last Error At</dt>
          <dd>{formatTimestamp(runtime.last_error_at)}</dd>
        </div>
      </dl>

      <div className="runtime-card__callouts">
        <div className="runtime-card__callout">
          <span className="runtime-card__callout-label">Status Reason</span>
          <p className="runtime-card__reason" data-testid={`runtime.reason.${runtime.runtime_id}`}>
            {runtime.status_reason}
          </p>
        </div>

        <div className={hasError ? "runtime-card__callout runtime-card__callout--error" : "runtime-card__callout"}>
          <span className="runtime-card__callout-label">Last Error</span>
          <p className="runtime-card__error" data-testid={`runtime.error.${runtime.runtime_id}`}>
            {runtime.last_error ?? "none"}
          </p>
        </div>
      </div>

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
