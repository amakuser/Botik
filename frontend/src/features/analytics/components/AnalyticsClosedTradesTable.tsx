import { AnalyticsClosedTrade } from "../../../shared/contracts";

type AnalyticsClosedTradesTableProps = {
  trades: AnalyticsClosedTrade[];
};

export function AnalyticsClosedTradesTable({ trades }: AnalyticsClosedTradesTableProps) {
  if (trades.length === 0) {
    return (
      <div className="surface-table-empty">
        <strong>No recent closed trades are available yet.</strong>
        <p className="panel-muted">Closed-trade history will appear here once the bounded analytics snapshot contains outcomes.</p>
      </div>
    );
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
              <td>
                <div className="surface-table__stack">
                  <span className="surface-table__primary">{trade.symbol}</span>
                  <span className="panel-muted">{trade.closed_at}</span>
                </div>
              </td>
              <td>
                <span className="surface-badge">{trade.scope}</span>
              </td>
              <td>
                <span className={trade.net_pnl < 0 ? "futures-pnl futures-pnl--negative" : "futures-pnl futures-pnl--positive"}>
                  {trade.net_pnl.toFixed(4)}
                </span>
              </td>
              <td>
                <span className={trade.was_profitable ? "surface-badge surface-badge--buy" : "surface-badge surface-badge--sell"}>
                  {trade.was_profitable ? "Win" : "Loss"}
                </span>
              </td>
              <td>{trade.closed_at}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
