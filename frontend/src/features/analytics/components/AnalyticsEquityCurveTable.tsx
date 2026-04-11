import { AnalyticsEquityPoint } from "../../../shared/contracts";

type AnalyticsEquityCurveTableProps = {
  points: AnalyticsEquityPoint[];
};

export function AnalyticsEquityCurveTable({ points }: AnalyticsEquityCurveTableProps) {
  if (points.length === 0) {
    return <p className="panel-muted">No closed-trade performance points are available yet.</p>;
  }

  return (
    <div className="surface-table-wrap">
      <table className="surface-table" data-testid="analytics.equity.table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Daily PnL</th>
            <th>Cumulative PnL</th>
          </tr>
        </thead>
        <tbody>
          {points.map((point, index) => (
            <tr key={`${point.date}-${index}`} data-testid={`analytics.equity.${point.date}`}>
              <td>{point.date}</td>
              <td>{point.daily_pnl.toFixed(4)}</td>
              <td>{point.cumulative_pnl.toFixed(4)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
