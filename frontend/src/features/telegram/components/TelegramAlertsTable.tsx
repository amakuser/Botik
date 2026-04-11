import { TelegramAlertEntry } from "../../../shared/contracts";

interface TelegramAlertsTableProps {
  alerts: TelegramAlertEntry[];
}

export function TelegramAlertsTable({ alerts }: TelegramAlertsTableProps) {
  return (
    <div className="surface-table-wrap">
      <table className="surface-table">
        <thead>
          <tr>
            <th>Type</th>
            <th>Message</th>
            <th>Delivered</th>
            <th>When</th>
          </tr>
        </thead>
        <tbody>
          {alerts.length === 0 ? (
            <tr>
              <td colSpan={4}>No recent Telegram alerts.</td>
            </tr>
          ) : (
            alerts.map((alert, index) => (
              <tr key={`${alert.alert_type}-${alert.ts ?? index}`} data-testid={`telegram.alert.${index}`}>
                <td>{alert.alert_type}</td>
                <td>{alert.message}</td>
                <td>{alert.delivered ? "yes" : "no"}</td>
                <td>{alert.ts ? new Date(alert.ts).toLocaleString() : "-"}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
