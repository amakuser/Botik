import { TrainingRunSummary } from "../../../shared/contracts";

type TrainingRunsTableProps = {
  runs: TrainingRunSummary[];
};

function badgeClass(value: string) {
  const normalized = value.trim().toLowerCase();
  if (normalized === "completed") {
    return "surface-badge surface-badge--buy";
  }
  if (normalized === "running" || normalized === "queued" || normalized === "starting") {
    return "surface-badge surface-badge--soft";
  }
  if (normalized === "failed" || normalized === "cancelled") {
    return "surface-badge surface-badge--sell";
  }
  return "surface-badge";
}

export function TrainingRunsTable({ runs }: TrainingRunsTableProps) {
  if (runs.length === 0) {
    return (
      <div className="surface-table-empty">
        <strong>Последних запусков обучения нет.</strong>
        <p className="panel-muted">История обучения появится после первых запусков.</p>
      </div>
    );
  }

  return (
    <div className="surface-table-wrap">
      <table className="surface-table">
        <thead>
          <tr>
            <th>ID запуска</th>
            <th>Скоуп</th>
            <th>Версия модели</th>
            <th>Статус</th>
            <th>Режим</th>
            <th>Начало</th>
            <th>Конец</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run, index) => (
            <tr key={run.run_id} data-testid={`models.run.${index}`}>
              <td>
                <div className="surface-table__stack">
                  <span className="surface-table__primary">{run.run_id}</span>
                  <div className="models-table__badges">
                    <span className={run.is_trained ? "surface-badge surface-badge--buy" : "surface-badge"}>
                      {run.is_trained ? "обучена" : "в процессе"}
                    </span>
                  </div>
                </div>
              </td>
              <td>
                <span className="surface-badge">{run.scope}</span>
              </td>
              <td>{run.model_version}</td>
              <td>
                <span className={badgeClass(run.status)}>{run.status}</span>
              </td>
              <td>
                <span className="surface-badge surface-badge--soft">{run.mode}</span>
              </td>
              <td>{run.started_at_utc}</td>
              <td>{run.finished_at_utc || "n/a"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
