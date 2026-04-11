import { TrainingRunSummary } from "../../../shared/contracts";

type TrainingRunsTableProps = {
  runs: TrainingRunSummary[];
};

export function TrainingRunsTable({ runs }: TrainingRunsTableProps) {
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
          {runs.length === 0 ? (
            <tr>
              <td colSpan={7}>No recent training runs available.</td>
            </tr>
          ) : (
            runs.map((run, index) => (
              <tr key={run.run_id} data-testid={`models.run.${index}`}>
                <td>{run.run_id}</td>
                <td>{run.scope}</td>
                <td>{run.model_version}</td>
                <td>{run.status}</td>
                <td>{run.mode}</td>
                <td>{run.started_at_utc}</td>
                <td>{run.finished_at_utc || "n/a"}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
