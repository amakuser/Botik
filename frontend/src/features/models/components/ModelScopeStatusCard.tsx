import { ModelsScopeStatus } from "../../../shared/contracts";

type ModelScopeStatusCardProps = {
  scopeStatus: ModelsScopeStatus;
};

function statusClass(ready: boolean) {
  return ready ? "runtime-state runtime-state--running" : "runtime-state runtime-state--offline";
}

function surfaceBadgeClass(value: string) {
  const normalized = value.trim().toLowerCase();
  if (normalized === "ready" || normalized === "completed") {
    return "surface-badge surface-badge--buy";
  }
  if (normalized === "running" || normalized === "candidate" || normalized === "online") {
    return "surface-badge surface-badge--soft";
  }
  if (normalized === "failed" || normalized === "stale" || normalized === "error") {
    return "surface-badge surface-badge--sell";
  }
  return "surface-badge";
}

export function ModelScopeStatusCard({ scopeStatus }: ModelScopeStatusCardProps) {
  return (
    <section className="panel models-scope-card" data-testid={`models.scope.${scopeStatus.scope}`}>
      <div className="runtime-card__header models-scope-card__header">
        <div className="runtime-card__title-block">
          <p className="models-scope-card__eyebrow">Scope Health</p>
          <h2>{scopeStatus.scope === "spot" ? "Spot Models" : "Futures Models"}</h2>
          <p className="panel-muted">Active manifest declaration plus the latest registry and training status.</p>
        </div>
        <span className={statusClass(scopeStatus.ready)}>{scopeStatus.ready ? "READY" : "PENDING"}</span>
      </div>

      <div className="runtime-card__signal-row models-scope-card__signal-row">
        <div className="runtime-card__signal models-scope-card__signal">
          <span className="runtime-card__signal-label">Active model</span>
          <strong>{scopeStatus.active_model}</strong>
          <span className="panel-muted">{scopeStatus.checkpoint_name || "No checkpoint declared"}</span>
        </div>
        <div className="runtime-card__signal models-scope-card__signal">
          <span className="runtime-card__signal-label">Latest training</span>
          <strong>{scopeStatus.latest_training_status}</strong>
          <span className="panel-muted">
            {scopeStatus.latest_training_mode} · {scopeStatus.latest_training_started_at}
          </span>
        </div>
      </div>

      <div className="models-scope-card__badge-row" aria-label={`${scopeStatus.scope} model status badges`}>
        <span className={surfaceBadgeClass(scopeStatus.latest_registry_status)}>
          Registry: {scopeStatus.latest_registry_status}
        </span>
        <span className={surfaceBadgeClass(scopeStatus.latest_training_status)}>
          Training: {scopeStatus.latest_training_status}
        </span>
      </div>

      <dl className="runtime-card__details models-scope-card__details">
        <div>
          <dt>Registry Model</dt>
          <dd>{scopeStatus.latest_registry_model}</dd>
        </div>
        <div>
          <dt>Registry Created</dt>
          <dd>{scopeStatus.latest_registry_created_at}</dd>
        </div>
        <div>
          <dt>Training Model</dt>
          <dd>{scopeStatus.latest_training_model_version}</dd>
        </div>
        <div>
          <dt>Training Mode</dt>
          <dd>{scopeStatus.latest_training_mode}</dd>
        </div>
        <div>
          <dt>Training Started</dt>
          <dd>{scopeStatus.latest_training_started_at}</dd>
        </div>
        <div>
          <dt>Checkpoint</dt>
          <dd>{scopeStatus.checkpoint_name || "n/a"}</dd>
        </div>
      </dl>

      <div className="runtime-card__callouts">
        <div className="runtime-card__callout">
          <p className="runtime-card__callout-label">Readiness reason</p>
          <p className="runtime-card__reason">{scopeStatus.status_reason}</p>
        </div>
      </div>
    </section>
  );
}
