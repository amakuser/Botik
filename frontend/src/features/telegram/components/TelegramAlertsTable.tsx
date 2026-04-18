import { TelegramAlertEntry } from "../../../shared/contracts";

interface TelegramAlertsTableProps {
  alerts: TelegramAlertEntry[];
}

export function TelegramAlertsTable({ alerts }: TelegramAlertsTableProps) {
  if (alerts.length === 0) {
    return (
      <div className="surface-table-empty">
        <strong>Последних алертов Telegram нет.</strong>
        <p className="panel-muted">История доставки появится после записи алертов.</p>
      </div>
    );
  }

  return (
    <div className="surface-table-wrap">
      <table className="surface-table">
        <thead>
          <tr>
            <th>Тип</th>
            <th>Сообщение</th>
            <th>Доставлено</th>
            <th>Когда</th>
          </tr>
        </thead>
        <tbody>
          {alerts.map((alert, index) => (
            <tr key={`${alert.alert_type}-${alert.ts ?? index}`} data-testid={`telegram.alert.${index}`}>
              <td>
                <div className="surface-table__stack">
                  <span className="surface-table__primary">{alert.alert_type}</span>
                  <span className="panel-muted">{alert.source}</span>
                </div>
              </td>
              <td>{alert.message}</td>
              <td>
                <span className={alert.delivered ? "surface-badge surface-badge--buy" : "surface-badge surface-badge--sell"}>
                  {alert.delivered ? "доставлено" : "не доставлено"}
                </span>
              </td>
              <td>{alert.ts ? new Date(alert.ts).toLocaleString() : "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
