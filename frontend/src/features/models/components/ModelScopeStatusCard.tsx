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
    <section
      className="panel models-scope-card"
      data-testid={`models.scope.${scopeStatus.scope}`}
      data-ui-role="scope-card"
      data-ui-scope={scopeStatus.scope}
      data-ui-state={scopeStatus.ready ? "ready" : "idle"}
    >
      <div className="runtime-card__header models-scope-card__header">
        <div className="runtime-card__title-block">
          <p className="models-scope-card__eyebrow">Состояние скоупа</p>
          <h2>{scopeStatus.scope === "spot" ? "Spot Модели" : "Futures Модели"}</h2>
          <p className="panel-muted">Активное объявление манифеста, последний статус реестра и обучения.</p>
        </div>
        <span
          className={statusClass(scopeStatus.ready)}
          data-ui-role="status-badge"
          data-ui-scope={scopeStatus.scope}
          data-ui-state={scopeStatus.ready ? "ready" : "idle"}
        >
          {scopeStatus.ready ? "ГОТОВО" : "В ОЖИДАНИИ"}
        </span>
      </div>

      <div className="runtime-card__signal-row models-scope-card__signal-row">
        <div
          className="runtime-card__signal models-scope-card__signal"
          data-ui-role="info-signal"
          data-ui-scope="active-model"
        >
          <span className="runtime-card__signal-label">Активная модель</span>
          <strong>{scopeStatus.active_model}</strong>
          <span className="panel-muted">{scopeStatus.checkpoint_name || "Чекпоинт не объявлен"}</span>
        </div>
        <div
          className="runtime-card__signal models-scope-card__signal"
          data-ui-role="info-signal"
          data-ui-scope="latest-training"
        >
          <span className="runtime-card__signal-label">Последнее обучение</span>
          <strong>{scopeStatus.latest_training_status}</strong>
          <span className="panel-muted">
            {scopeStatus.latest_training_mode} · {scopeStatus.latest_training_started_at}
          </span>
        </div>
      </div>

      <div className="models-scope-card__badge-row" aria-label={`${scopeStatus.scope} model status badges`}>
        <span
          className={surfaceBadgeClass(scopeStatus.latest_registry_status)}
          data-ui-role="status-badge"
          data-ui-scope={`${scopeStatus.scope}-registry`}
          data-ui-state={scopeStatus.latest_registry_status.trim().toLowerCase()}
        >
          Реестр: {scopeStatus.latest_registry_status}
        </span>
        <span
          className={surfaceBadgeClass(scopeStatus.latest_training_status)}
          data-ui-role="status-badge"
          data-ui-scope={`${scopeStatus.scope}-training`}
          data-ui-state={scopeStatus.latest_training_status.trim().toLowerCase()}
        >
          Обучение: {scopeStatus.latest_training_status}
        </span>
      </div>

      <dl className="runtime-card__details models-scope-card__details">
        <div>
          <dt>Модель реестра</dt>
          <dd>{scopeStatus.latest_registry_model}</dd>
        </div>
        <div>
          <dt>Создана в реестре</dt>
          <dd>{scopeStatus.latest_registry_created_at}</dd>
        </div>
        <div>
          <dt>Модель обучения</dt>
          <dd>{scopeStatus.latest_training_model_version}</dd>
        </div>
        <div>
          <dt>Режим обучения</dt>
          <dd>{scopeStatus.latest_training_mode}</dd>
        </div>
        <div>
          <dt>Обучение начато</dt>
          <dd>{scopeStatus.latest_training_started_at}</dd>
        </div>
        <div>
          <dt>Чекпоинт</dt>
          <dd>{scopeStatus.checkpoint_name || "n/a"}</dd>
        </div>
      </dl>

      <div className="runtime-card__callouts">
        <div
          className="runtime-card__callout"
          data-ui-role="status-callout"
          data-ui-scope={scopeStatus.scope}
          data-ui-kind="info"
        >
          <p className="runtime-card__callout-label">Причина готовности</p>
          <p className="runtime-card__reason">{scopeStatus.status_reason}</p>
        </div>
      </div>
    </section>
  );
}
