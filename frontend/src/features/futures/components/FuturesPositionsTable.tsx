import type { FuturesPosition } from "../../../shared/contracts";

interface FuturesPositionsTableProps {
  positions: FuturesPosition[];
}

function formatNumber(value: number | null | undefined, decimals = 2) {
  if (value === null || value === undefined) {
    return "n/a";
  }
  return value.toFixed(decimals);
}

function pnlClassName(value: number | null | undefined) {
  if (value === null || value === undefined || value === 0) {
    return "futures-pnl";
  }
  return value > 0 ? "futures-pnl futures-pnl--positive" : "futures-pnl futures-pnl--negative";
}

export function FuturesPositionsTable({ positions }: FuturesPositionsTableProps) {
  if (positions.length === 0) {
    return <p className="panel-muted surface-table-empty">No open futures positions are available in the current read model.</p>;
  }

  return (
    <div className="surface-table-wrap" data-testid="futures.positions.table">
      <table className="surface-table">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Side</th>
            <th>Qty</th>
            <th>Entry</th>
            <th>Mark</th>
            <th>uPnL</th>
            <th>Protection</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((position) => (
            <tr
              key={`${position.account_type}:${position.symbol}:${position.side}:${position.position_idx}`}
              data-testid={`futures.position.${position.symbol}.${position.side}`}
            >
              <td className="surface-table__primary">
                <div className="surface-table__stack">
                  <strong>{position.symbol}</strong>
                  <span className="panel-muted">{position.strategy_owner ?? "unassigned strategy"}</span>
                </div>
              </td>
              <td>
                <span className={position.side === "Buy" ? "surface-badge surface-badge--buy" : "surface-badge surface-badge--sell"}>
                  {position.side}
                </span>
              </td>
              <td>
                <div className="surface-table__stack">
                  <strong>{formatNumber(position.qty, 4)}</strong>
                  <span className="panel-muted">
                    {position.leverage ? `${formatNumber(position.leverage, 1)}x` : "n/a"} · {position.margin_mode ?? "n/a"}
                  </span>
                </div>
              </td>
              <td>
                <div className="surface-table__stack">
                  <strong>{formatNumber(position.entry_price, 2)}</strong>
                  <span className="panel-muted">liq {formatNumber(position.liq_price, 2)}</span>
                </div>
              </td>
              <td>{formatNumber(position.mark_price, 2)}</td>
              <td>
                <span className={pnlClassName(position.unrealized_pnl)}>{formatNumber(position.unrealized_pnl, 4)}</span>
              </td>
              <td>
                <div className="surface-table__stack">
                  <span className="surface-badge surface-badge--soft">{position.protection_status}</span>
                  <span className="panel-muted">{position.recovered_from_exchange ? "reconciled from exchange" : "native model state"}</span>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
