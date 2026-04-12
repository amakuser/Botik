import { ModelRegistryEntry } from "../../../shared/contracts";

type ModelsRegistryTableProps = {
  entries: ModelRegistryEntry[];
};

function badgeClass(value: string) {
  const normalized = value.trim().toLowerCase();
  if (normalized === "ready") {
    return "surface-badge surface-badge--buy";
  }
  if (normalized === "candidate" || normalized === "promoted") {
    return "surface-badge surface-badge--soft";
  }
  if (normalized === "failed" || normalized === "stale") {
    return "surface-badge surface-badge--sell";
  }
  return "surface-badge";
}

export function ModelsRegistryTable({ entries }: ModelsRegistryTableProps) {
  if (entries.length === 0) {
    return (
      <div className="surface-table-empty">
        <strong>No model registry entries available.</strong>
        <p className="panel-muted">The bounded snapshot does not include any registry rows yet.</p>
      </div>
    );
  }

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
          {entries.map((entry, index) => (
            <tr key={`${entry.model_id}-${entry.created_at_utc}`} data-testid={`models.registry.${index}`}>
              <td>
                <div className="surface-table__stack">
                  <span className="surface-table__primary">{entry.model_id}</span>
                  <div className="models-table__badges">
                    {entry.is_declared_active ? (
                      <span className="surface-badge surface-badge--soft">Declared active</span>
                    ) : (
                      <span className="surface-badge">Passive</span>
                    )}
                  </div>
                </div>
              </td>
              <td>
                <span className="surface-badge">{entry.scope}</span>
              </td>
              <td>
                <span className={badgeClass(entry.status)}>{entry.status}</span>
              </td>
              <td>
                <span className="surface-table__primary">
                  {entry.quality_score !== null && entry.quality_score !== undefined ? entry.quality_score.toFixed(2) : "n/a"}
                </span>
              </td>
              <td>
                <div className="surface-table__stack">
                  <span>{entry.policy}</span>
                  <span className="panel-muted">Source: {entry.source_mode}</span>
                </div>
              </td>
              <td>
                <div className="surface-table__stack">
                  <span>{entry.artifact_name || "n/a"}</span>
                  <span className="panel-muted">{entry.created_at_utc}</span>
                </div>
              </td>
              <td>{entry.created_at_utc}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
