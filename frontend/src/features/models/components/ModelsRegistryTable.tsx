import { ModelRegistryEntry } from "../../../shared/contracts";

type ModelsRegistryTableProps = {
  entries: ModelRegistryEntry[];
};

export function ModelsRegistryTable({ entries }: ModelsRegistryTableProps) {
  return (
    <div className="surface-table-wrap">
      <table className="surface-table">
        <thead>
          <tr>
            <th>Model</th>
            <th>Scope</th>
            <th>Status</th>
            <th>Quality</th>
            <th>Policy / Source</th>
            <th>Artifact</th>
            <th>Created</th>
          </tr>
        </thead>
        <tbody>
          {entries.length === 0 ? (
            <tr>
              <td colSpan={7}>No model registry entries available.</td>
            </tr>
          ) : (
            entries.map((entry, index) => (
              <tr key={`${entry.model_id}-${entry.created_at_utc}`} data-testid={`models.registry.${index}`}>
                <td>
                  {entry.model_id}
                  {entry.is_declared_active ? " (active)" : ""}
                </td>
                <td>{entry.scope}</td>
                <td>{entry.status}</td>
                <td>{entry.quality_score !== null && entry.quality_score !== undefined ? entry.quality_score.toFixed(2) : "n/a"}</td>
                <td>
                  {entry.policy} / {entry.source_mode}
                </td>
                <td>{entry.artifact_name || "n/a"}</td>
                <td>{entry.created_at_utc}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
