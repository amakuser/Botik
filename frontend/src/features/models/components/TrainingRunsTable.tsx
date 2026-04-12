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
        <strong>No recent training runs available.</strong>
        <p className="panel-muted">Recent bounded training history will appear here once runs are recorded.</p>
      </div>
    );
  }

  return (
    <div className="surface-table-wrap">
      <table className="surface-table">
        <thead>
          <tr>
            <th>Run ID</th>
            <th>Scope</th>
            <th>Model Version</th>
            <th>Status</th>
            <th>Mode</th>
            <th>Started</th>
            <th>Finished</th>
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
                      {run.is_trained ? "trained" : "in progress"}
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
