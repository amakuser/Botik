import { TelegramErrorEntry } from "../../../shared/contracts";

interface TelegramErrorsTableProps {
  errors: TelegramErrorEntry[];
}

export function TelegramErrorsTable({ errors }: TelegramErrorsTableProps) {
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
          {errors.length === 0 ? (
            <tr>
              <td colSpan={4}>No recent Telegram errors.</td>
            </tr>
          ) : (
            errors.map((error, index) => (
              <tr key={`${error.source}-${error.ts ?? index}`} data-testid={`telegram.error.${index}`}>
                <td>{error.source}</td>
                <td>{error.status}</td>
                <td>{error.error}</td>
                <td>{error.ts ? new Date(error.ts).toLocaleString() : "-"}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
