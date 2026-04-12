import { TelegramErrorEntry } from "../../../shared/contracts";

interface TelegramErrorsTableProps {
  errors: TelegramErrorEntry[];
}

export function TelegramErrorsTable({ errors }: TelegramErrorsTableProps) {
  if (errors.length === 0) {
    return (
      <div className="surface-table-empty">
        <strong>No recent Telegram errors.</strong>
        <p className="panel-muted">Warnings and delivery failures will appear here once the bounded snapshot includes error rows.</p>
      </div>
    );
  }

  return (
    <div className="surface-table-wrap">
      <table className="surface-table">
        <thead>
          <tr>
            <th>Source</th>
            <th>Status</th>
            <th>Error</th>
            <th>When</th>
          </tr>
        </thead>
        <tbody>
          {errors.map((error, index) => (
            <tr key={`${error.source}-${error.ts ?? index}`} data-testid={`telegram.error.${index}`}>
              <td>{error.source}</td>
              <td>
                <span className={error.status === "warning" ? "surface-badge surface-badge--soft" : "surface-badge surface-badge--sell"}>
                  {error.status}
                </span>
              </td>
              <td>{error.error}</td>
              <td>{error.ts ? new Date(error.ts).toLocaleString() : "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
