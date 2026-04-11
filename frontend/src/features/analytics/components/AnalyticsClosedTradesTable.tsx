import { AnalyticsClosedTrade } from "../../../shared/contracts";

type AnalyticsClosedTradesTableProps = {
  trades: AnalyticsClosedTrade[];
};

export function AnalyticsClosedTradesTable({ trades }: AnalyticsClosedTradesTableProps) {
  if (trades.length === 0) {
    return <p className="panel-muted">No recent closed trades are available yet.</p>;
  }

  return (
    <div className="surface-table-wrap">
      <table className="surface-table" data-testid="analytics.closed-trades.table">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Scope</th>
            <th>Net PnL</th>
            <th>Result</th>
            <th>Closed At</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((trade, index) => (
            <tr key={`${trade.symbol}-${trade.closed_at}-${index}`} data-testid={`analytics.trade.${index}`}>
              <td>{trade.symbol}</td>
              <td>{trade.scope}</td>
              <td>{trade.net_pnl.toFixed(4)}</td>
              <td>{trade.was_profitable ? "Win" : "Loss"}</td>
              <td>{trade.closed_at}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
