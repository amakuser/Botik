import { ModelsScopeStatus } from "../../../shared/contracts";

type ModelScopeStatusCardProps = {
  scopeStatus: ModelsScopeStatus;
};

function statusClass(ready: boolean) {
  return ready ? "runtime-state runtime-state--running" : "runtime-state runtime-state--offline";
}

export function ModelScopeStatusCard({ scopeStatus }: ModelScopeStatusCardProps) {
  return (
    <section className="panel" data-testid={`models.scope.${scopeStatus.scope}`}>
      <div className="runtime-card__header">
        <div>
          <h2>{scopeStatus.scope === "spot" ? "Spot Models" : "Futures Models"}</h2>
          <p className="panel-muted">Active manifest declaration plus the latest registry and training status.</p>
        </div>
        <span className={statusClass(scopeStatus.ready)}>{scopeStatus.ready ? "READY" : "PENDING"}</span>
      </div>

      <dl className="runtime-card__details">
        <div>
          <dt>Active Model</dt>
          <dd>{scopeStatus.active_model}</dd>
        </div>
        <div>
          <dt>Checkpoint</dt>
          <dd>{scopeStatus.checkpoint_name || "n/a"}</dd>
        </div>
        <div>
          <dt>Latest Registry Model</dt>
          <dd>{scopeStatus.latest_registry_model}</dd>
        </div>
        <div>
          <dt>Registry Status</dt>
          <dd>{scopeStatus.latest_registry_status}</dd>
        </div>
        <div>
          <dt>Latest Training Model</dt>
          <dd>{scopeStatus.latest_training_model_version}</dd>
        </div>
        <div>
          <dt>Training Status</dt>
          <dd>{scopeStatus.latest_training_status}</dd>
        </div>
        <div>
          <dt>Training Mode</dt>
          <dd>{scopeStatus.latest_training_mode}</dd>
        </div>
        <div>
          <dt>Started</dt>
          <dd>{scopeStatus.latest_training_started_at}</dd>
        </div>
      </dl>

      <p className="runtime-card__reason">{scopeStatus.status_reason}</p>
    </section>
  );
}
